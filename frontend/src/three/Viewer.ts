import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { SELECTION_COLOR } from '../lib/colors'

export interface PickEvent {
  globalId: string | null
  clientX: number
  clientY: number
}

export interface ViewerCallbacks {
  onHover?: (event: PickEvent) => void
  onSelect?: (event: PickEvent) => void
}

export type CameraView = 'iso' | 'top' | 'front' | 'side'

interface Entry {
  mesh: THREE.Mesh
  material: THREE.MeshStandardMaterial
  edges: THREE.LineSegments | null
  displayColor: THREE.Color
  baseOpacity: number
  ghosted: boolean
}

const HOVER_EMISSIVE = new THREE.Color('#38bdf8')
const BLACK = new THREE.Color(0x000000)
const SELECTION = new THREE.Color(SELECTION_COLOR)
const GHOST_OPACITY = 0.07
const EDGE_OPACITY = 0.45
const EDGE_LIMIT = 4000 // above this many meshes, skip edge overlays and shadows to keep the frame rate up

/**
 * Thin wrapper around a Three.js scene that knows about IFC elements by GlobalId.
 * It owns the render loop, picking, per-element colouring, visibility, ghosting,
 * a horizontal section plane and animated camera presets.
 */
export class Viewer {
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera: THREE.PerspectiveCamera
  private readonly controls: OrbitControls
  private readonly raycaster = new THREE.Raycaster()
  private readonly pointer = new THREE.Vector2(2, 2)
  private readonly root = new THREE.Group()
  private readonly entries = new Map<string, Entry>()
  private readonly resizeObserver: ResizeObserver
  private readonly keyLight: THREE.DirectionalLight
  private readonly section = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0)
  private readonly sectionPlanes: THREE.Plane[] = []
  private readonly bounds = new THREE.Box3()
  private grid: THREE.GridHelper | null = null
  private ground: THREE.Mesh | null = null
  private sectionHelper: THREE.Mesh | null = null
  private selectedId: string | null = null
  private hoveredId: string | null = null
  private pointerDirty = false
  private pointerDownAt = { x: 0, y: 0 }
  private tween: { from: THREE.Vector3; to: THREE.Vector3; fromTarget: THREE.Vector3; toTarget: THREE.Vector3; start: number } | null = null
  private disposed = false
  /** Frames are only drawn when something changed, so an idle view costs no GPU time. */
  private needsRender = true
  private loadToken = 0
  /** True until the user moves the camera: while it holds, resizes re-frame the model. */
  private autoFit = true

  private readonly container: HTMLElement
  private readonly callbacks: ViewerCallbacks

  constructor(container: HTMLElement, callbacks: ViewerCallbacks = {}) {
    this.container = container
    this.callbacks = callbacks
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.0
    this.renderer.localClippingEnabled = true
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.domElement.style.display = 'block'
    // setSize(..., false) leaves the CSS size alone, so pin it to the container; otherwise a
    // high-DPI screen shows the canvas at its pixel size and crops the model.
    this.renderer.domElement.style.width = '100%'
    this.renderer.domElement.style.height = '100%'
    this.renderer.domElement.style.touchAction = 'none'
    container.appendChild(this.renderer.domElement)

    const pmrem = new THREE.PMREMGenerator(this.renderer)
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    this.scene.environmentIntensity = 0.35
    pmrem.dispose()

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.05, 5000)
    this.camera.position.set(20, 15, 20)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI * 0.95
    this.controls.addEventListener('start', () => {
      this.tween = null
      this.autoFit = false
    })
    this.controls.addEventListener('change', this.invalidate)

    const hemisphere = new THREE.HemisphereLight(0xffffff, 0x334155, 0.9)
    this.keyLight = new THREE.DirectionalLight(0xfff7ed, 1.9)
    this.keyLight.castShadow = true
    this.keyLight.shadow.mapSize.set(2048, 2048)
    this.keyLight.shadow.bias = -0.0005
    this.keyLight.shadow.normalBias = 0.02
    const fill = new THREE.DirectionalLight(0xbfdbfe, 0.45)
    fill.position.set(-30, 20, -20)
    this.scene.add(hemisphere, this.keyLight, this.keyLight.target, fill, this.root)

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(container)
    this.resize()

    const canvas = this.renderer.domElement
    canvas.addEventListener('pointermove', this.onPointerMove)
    canvas.addEventListener('pointerdown', this.onPointerDown)
    canvas.addEventListener('pointerup', this.onPointerUp)
    canvas.addEventListener('pointerleave', this.onPointerLeave)
    canvas.addEventListener('pointercancel', this.onPointerLeave)
    canvas.addEventListener('dblclick', this.onDoubleClick)

    this.renderer.setAnimationLoop(this.frame)
  }

  // -- loading ------------------------------------------------------------------------

  async load(url: string): Promise<{ meshCount: number }> {
    this.clear()
    const token = ++this.loadToken
    const gltf = await new GLTFLoader().loadAsync(url)
    // A newer load (or clear) started while this file was downloading: drop it, or two models end up on screen.
    if (this.disposed || token !== this.loadToken) return { meshCount: 0 }
    const meshes: THREE.Mesh[] = []
    gltf.scene.traverse((object) => {
      if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh)
    })
    const detailed = meshes.length <= EDGE_LIMIT

    for (const mesh of meshes) {
      const source = mesh.material as THREE.MeshStandardMaterial
      const opacity = source.opacity ?? 1
      const material = new THREE.MeshStandardMaterial({
        color: source.color?.clone() ?? new THREE.Color('#cbd5e1'),
        opacity,
        transparent: opacity < 1,
        roughness: 0.82,
        metalness: 0,
        side: THREE.DoubleSide,
        polygonOffset: detailed,
        polygonOffsetFactor: 1,
        polygonOffsetUnits: 1,
        clippingPlanes: this.sectionPlanes,
        clipShadows: true,
      })
      mesh.material = material
      mesh.matrixAutoUpdate = false
      mesh.updateMatrix()
      mesh.castShadow = detailed
      mesh.receiveShadow = detailed

      let edges: THREE.LineSegments | null = null
      if (detailed) {
        edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(mesh.geometry, 20),
          new THREE.LineBasicMaterial({
            color: 0x0b1220,
            transparent: true,
            opacity: EDGE_OPACITY,
            clippingPlanes: this.sectionPlanes,
          }),
        )
        edges.matrix.copy(mesh.matrix)
        edges.matrixAutoUpdate = false
        edges.raycast = () => undefined
        this.root.add(edges)
      }

      this.root.add(mesh)
      this.entries.set(mesh.name, {
        mesh,
        material,
        edges,
        displayColor: material.color.clone(),
        baseOpacity: opacity,
        ghosted: false,
      })
    }

    this.bounds.setFromObject(this.root)
    this.addGroundAndGrid()
    this.fitShadowCamera()
    this.fitToView(undefined, false)
    this.invalidate()
    return { meshCount: meshes.length }
  }

  clear(): void {
    this.loadToken++
    for (const entry of this.entries.values()) {
      entry.mesh.geometry.dispose()
      entry.material.dispose()
      if (entry.edges) {
        entry.edges.geometry.dispose()
        ;(entry.edges.material as THREE.Material).dispose()
      }
    }
    this.entries.clear()
    this.root.clear()
    for (const helper of [this.grid, this.ground, this.sectionHelper]) {
      if (!helper) continue
      this.scene.remove(helper)
      helper.geometry.dispose()
      ;(helper.material as THREE.Material).dispose()
    }
    this.grid = null
    this.ground = null
    this.sectionHelper = null
    this.bounds.makeEmpty()
    this.selectedId = null
    this.hoveredId = null
    this.sectionPlanes.length = 0
    this.invalidate()
  }

  // -- appearance ------------------------------------------------------------------------

  /**
   * Recolour every element. `color` returns a CSS hex colour or null to keep the current one;
   * `opacity` optionally overrides the element's own opacity (glass in material mode).
   */
  applyColors(color: (globalId: string) => string | null, opacity?: (globalId: string) => number | null): void {
    for (const [id, entry] of this.entries) {
      const hex = color(id)
      if (hex) entry.displayColor.set(hex)
      const value = opacity?.(id)
      if (value !== undefined && value !== null) entry.baseOpacity = value
      this.paint(id, entry)
    }
  }

  setVisibility(isVisible: (globalId: string) => boolean): void {
    for (const [id, entry] of this.entries) {
      const visible = isVisible(id)
      entry.mesh.visible = visible
      if (entry.edges) entry.edges.visible = visible
    }
    this.invalidate()
    if (this.hoveredId && !this.entries.get(this.hoveredId)?.mesh.visible) this.setHovered(null)
  }

  /** Ghosted elements stay as faint context: barely visible, no shadows, not pickable. */
  setGhosted(isGhosted: (globalId: string) => boolean): void {
    for (const [id, entry] of this.entries) {
      entry.ghosted = isGhosted(id)
      this.paint(id, entry)
    }
    if (this.hoveredId && this.entries.get(this.hoveredId)?.ghosted) this.setHovered(null)
  }

  setSelected(globalId: string | null): void {
    const previous = this.selectedId
    this.selectedId = globalId
    if (previous) this.repaint(previous)
    if (globalId) this.repaint(globalId)
  }

  /** Cut the model horizontally. `height` runs from 0 (bottom of the model) to 1 (top). */
  setSection(enabled: boolean, height: number): void {
    const planesBefore = this.sectionPlanes.length
    this.sectionPlanes.length = 0
    if (enabled && !this.bounds.isEmpty()) {
      const y = THREE.MathUtils.lerp(this.bounds.min.y, this.bounds.max.y, THREE.MathUtils.clamp(height, 0, 1))
      this.section.constant = y
      this.sectionPlanes.push(this.section)
      this.updateSectionHelper(y)
    } else if (this.sectionHelper) {
      this.sectionHelper.visible = false
    }
    this.invalidate()
    // Materials share the plane array, so moving the plane needs nothing more. Only switching the
    // cut on or off changes the plane count, and that is when the programs have to be rebuilt.
    if (this.sectionPlanes.length === planesBefore) return
    for (const entry of this.entries.values()) {
      entry.material.needsUpdate = true
      if (entry.edges) (entry.edges.material as THREE.Material).needsUpdate = true
    }
  }

  /** Highlight an element from outside the 3D view, e.g. while its row in a list is hovered. */
  setHighlighted(globalId: string | null): void {
    const entry = globalId ? this.entries.get(globalId) : null
    this.setHovered(entry && entry.mesh.visible ? globalId : null)
  }

  private setHovered(globalId: string | null): void {
    if (this.hoveredId === globalId) return
    const previous = this.hoveredId
    this.hoveredId = globalId
    if (previous) this.repaint(previous)
    if (globalId) this.repaint(globalId)
  }

  private repaint(id: string): void {
    const entry = this.entries.get(id)
    if (entry) this.paint(id, entry)
  }

  private paint(id: string, entry: Entry): void {
    const material = entry.material
    const isSelected = id === this.selectedId
    const isHovered = id === this.hoveredId && !entry.ghosted
    const ghost = entry.ghosted && !isSelected
    const opacity = ghost ? GHOST_OPACITY : entry.baseOpacity
    const transparent = opacity < 0.999

    if (isSelected) {
      material.color.copy(entry.displayColor).lerp(SELECTION, 0.55)
      material.emissive.set(SELECTION_COLOR)
      material.emissiveIntensity = 0.45
    } else {
      material.color.copy(entry.displayColor)
      material.emissive.copy(isHovered ? HOVER_EMISSIVE : BLACK)
      material.emissiveIntensity = isHovered ? 0.25 : 0
    }
    if (material.transparent !== transparent) material.needsUpdate = true
    material.opacity = opacity
    material.transparent = transparent
    material.depthWrite = !ghost
    entry.mesh.castShadow = !ghost && this.entries.size <= EDGE_LIMIT
    entry.mesh.renderOrder = ghost ? 1 : 0
    if (entry.edges) {
      const edgeMaterial = entry.edges.material as THREE.LineBasicMaterial
      edgeMaterial.opacity = ghost ? 0.06 : EDGE_OPACITY
      edgeMaterial.color.set(isSelected ? 0x0c4a6e : 0x0b1220)
    }
    this.invalidate()
  }

  // -- camera -------------------------------------------------------------------------------

  fitToView(globalIds?: string[], animate = true): void {
    this.autoFit = !globalIds
    const box = new THREE.Box3()
    const targets = globalIds
      ? globalIds.map((id) => this.entries.get(id)?.mesh).filter((m): m is THREE.Mesh => !!m)
      : [...this.entries.values()].filter((e) => e.mesh.visible && !e.ghosted).map((e) => e.mesh)
    for (const mesh of targets) box.expandByObject(mesh)
    if (box.isEmpty()) {
      if (globalIds || this.bounds.isEmpty()) return
      box.copy(this.bounds)
    }
    const direction = this.camera.position.clone().sub(this.controls.target)
    if (direction.lengthSq() < 1e-6) direction.set(1, 0.75, 1)
    this.frameBox(box, direction.normalize(), animate)
  }

  setView(view: CameraView): void {
    const box = this.bounds.isEmpty() ? null : this.bounds
    if (!box) return
    const directions: Record<CameraView, THREE.Vector3> = {
      iso: new THREE.Vector3(1, 0.75, 1),
      top: new THREE.Vector3(0, 1, 0.0001),
      front: new THREE.Vector3(0, 0.08, 1),
      side: new THREE.Vector3(1, 0.08, 0),
    }
    this.frameBox(box, directions[view].normalize(), true)
  }

  private frameBox(box: THREE.Box3, direction: THREE.Vector3, animate: boolean): void {
    const center = box.getCenter(new THREE.Vector3())
    const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.5)
    const vertical = THREE.MathUtils.degToRad(this.camera.fov / 2)
    const horizontal = Math.atan(Math.tan(vertical) * this.camera.aspect)
    const distance = (radius / Math.sin(Math.min(vertical, horizontal))) * 1.02
    const position = center.clone().addScaledVector(direction, distance)
    this.camera.near = Math.max(distance / 1000, 0.01)
    this.camera.far = distance * 50
    this.camera.updateProjectionMatrix()
    if (!animate) {
      this.camera.position.copy(position)
      this.controls.target.copy(center)
      this.controls.update()
      this.invalidate()
      return
    }
    this.tween = {
      from: this.camera.position.clone(),
      to: position,
      fromTarget: this.controls.target.clone(),
      toTarget: center,
      start: performance.now(),
    }
  }

  /**
   * Render one frame and return it as a PNG data URL. The WebGL canvas is transparent (the
   * backdrop is CSS), so the frame is composited onto a matching gradient instead of exporting
   * a see-through image that turns white or black in other programs.
   */
  screenshot(): string {
    this.renderer.render(this.scene, this.camera)
    const source = this.renderer.domElement
    const canvas = document.createElement('canvas')
    canvas.width = source.width
    canvas.height = source.height
    const context = canvas.getContext('2d')
    if (!context) return source.toDataURL('image/png')
    const gradient = context.createLinearGradient(0, 0, 0, canvas.height)
    gradient.addColorStop(0, '#0d1626')
    gradient.addColorStop(1, '#070b14')
    context.fillStyle = gradient
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(source, 0, 0)
    return canvas.toDataURL('image/png')
  }

  private addGroundAndGrid(): void {
    const box = this.bounds
    if (box.isEmpty()) return
    const sizeVec = box.getSize(new THREE.Vector3())
    const size = Math.ceil(Math.max(sizeVec.x, sizeVec.z) * 2.5)
    const center = box.getCenter(new THREE.Vector3())
    const divisions = Math.max(10, Math.min(120, Math.round(size)))
    this.grid = new THREE.GridHelper(size, divisions, 0x263349, 0x1a2538)
    this.grid.position.set(center.x, box.min.y - 0.02, center.z)
    ;(this.grid.material as THREE.Material).transparent = true
    ;(this.grid.material as THREE.Material).opacity = 0.6
    this.scene.add(this.grid)

    this.ground = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size),
      new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.35 }),
    )
    this.ground.rotation.x = -Math.PI / 2
    this.ground.position.set(center.x, box.min.y - 0.01, center.z)
    this.ground.receiveShadow = true
    this.ground.raycast = () => undefined
    this.scene.add(this.ground)
  }

  private fitShadowCamera(): void {
    const box = this.bounds
    if (box.isEmpty()) return
    const center = box.getCenter(new THREE.Vector3())
    const radius = box.getSize(new THREE.Vector3()).length() / 2
    this.keyLight.position.copy(center).add(new THREE.Vector3(0.6, 1, 0.35).normalize().multiplyScalar(radius * 2))
    this.keyLight.target.position.copy(center)
    const cam = this.keyLight.shadow.camera
    cam.left = cam.bottom = -radius * 1.2
    cam.right = cam.top = radius * 1.2
    cam.near = 0.1
    cam.far = radius * 5
    cam.updateProjectionMatrix()
  }

  private updateSectionHelper(y: number): void {
    const box = this.bounds
    if (!this.sectionHelper) {
      const size = box.getSize(new THREE.Vector3())
      this.sectionHelper = new THREE.Mesh(
        new THREE.PlaneGeometry(size.x * 1.15, size.z * 1.15),
        new THREE.MeshBasicMaterial({
          color: 0x38bdf8,
          transparent: true,
          opacity: 0.08,
          side: THREE.DoubleSide,
          depthWrite: false,
        }),
      )
      this.sectionHelper.rotation.x = -Math.PI / 2
      this.sectionHelper.raycast = () => undefined
      this.scene.add(this.sectionHelper)
    }
    const center = box.getCenter(new THREE.Vector3())
    this.sectionHelper.position.set(center.x, y, center.z)
    this.sectionHelper.visible = true
  }

  private invalidate = (): void => {
    this.needsRender = true
  }

  // -- interaction -----------------------------------------------------------------------------

  private lastPointer = { clientX: 0, clientY: 0 }

  /** Convert a pointer event to normalised device coordinates for the raycaster. */
  private updatePointer(event: PointerEvent): void {
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1)
    this.lastPointer = { clientX: event.clientX, clientY: event.clientY }
  }

  private onPointerMove = (event: PointerEvent): void => {
    // Hovering is a mouse thing: a finger has no hover, and while a button is held the camera
    // is being dragged, where picking every frame only costs time and makes the model flicker.
    if (event.pointerType === 'touch' || event.buttons !== 0) return
    this.updatePointer(event)
    this.pointerDirty = true
  }

  private onPointerDown = (event: PointerEvent): void => {
    this.pointerDownAt = { x: event.clientX, y: event.clientY }
  }

  private onPointerUp = (event: PointerEvent): void => {
    const moved = Math.hypot(event.clientX - this.pointerDownAt.x, event.clientY - this.pointerDownAt.y)
    if (moved > 4 || event.button !== 0) return
    // Touch taps and some clicks arrive without a preceding pointermove, so pick from the click position itself.
    this.updatePointer(event)
    const hit = this.pick()
    this.callbacks.onSelect?.({ globalId: hit, clientX: event.clientX, clientY: event.clientY })
  }

  /** Double-click zooms to the element under the pointer, or back to the whole model on empty space. */
  private onDoubleClick = (event: MouseEvent): void => {
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1)
    const hit = this.pick()
    this.fitToView(hit ? [hit] : undefined)
  }

  private onPointerLeave = (): void => {
    this.pointer.set(2, 2)
    this.pointerDirty = false
    this.setHovered(null)
    this.callbacks.onHover?.({ globalId: null, clientX: 0, clientY: 0 })
  }

  private pick(): string | null {
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const meshes = [...this.entries.values()].filter((e) => e.mesh.visible && !e.ghosted).map((e) => e.mesh)
    const hits = this.raycaster.intersectObjects(meshes, false)
    // Ignore the parts of a hit that the section plane has cut away.
    const hit = this.sectionPlanes.length ? hits.find((h) => this.section.distanceToPoint(h.point) >= 0) : hits[0]
    return hit ? hit.object.name : null
  }

  private frame = (): void => {
    if (this.disposed) return
    if (this.tween) {
      const t = Math.min(1, (performance.now() - this.tween.start) / 450)
      const k = 1 - Math.pow(1 - t, 3)
      this.camera.position.lerpVectors(this.tween.from, this.tween.to, k)
      this.controls.target.lerpVectors(this.tween.fromTarget, this.tween.toTarget, k)
      if (t >= 1) this.tween = null
      this.needsRender = true
    }
    if (this.pointerDirty) {
      this.pointerDirty = false
      const hit = this.pick()
      if (hit !== this.hoveredId) {
        this.setHovered(hit)
        this.callbacks.onHover?.({ globalId: hit, ...this.lastPointer })
      }
    }
    // With damping the controls keep moving for a few frames after the pointer is released.
    if (this.controls.update()) this.needsRender = true
    if (!this.needsRender) return
    this.needsRender = false
    this.renderer.render(this.scene, this.camera)
  }

  private resize(): void {
    const { clientWidth, clientHeight } = this.container
    if (clientWidth === 0 || clientHeight === 0) return
    this.renderer.setSize(clientWidth, clientHeight, false)
    this.camera.aspect = clientWidth / clientHeight
    this.camera.updateProjectionMatrix()
    this.invalidate()
    if (this.autoFit && !this.bounds.isEmpty()) this.fitToView(undefined, false)
  }

  dispose(): void {
    this.disposed = true
    this.renderer.setAnimationLoop(null)
    this.resizeObserver.disconnect()
    const canvas = this.renderer.domElement
    canvas.removeEventListener('pointermove', this.onPointerMove)
    canvas.removeEventListener('pointerdown', this.onPointerDown)
    canvas.removeEventListener('pointerup', this.onPointerUp)
    canvas.removeEventListener('pointerleave', this.onPointerLeave)
    canvas.removeEventListener('pointercancel', this.onPointerLeave)
    canvas.removeEventListener('dblclick', this.onDoubleClick)
    this.clear()
    this.scene.environment?.dispose()
    this.controls.dispose()
    this.renderer.dispose()
    canvas.remove()
  }
}
