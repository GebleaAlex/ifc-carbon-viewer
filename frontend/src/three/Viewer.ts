import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
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

interface Entry {
  mesh: THREE.Mesh
  material: THREE.MeshStandardMaterial
  edges: THREE.LineSegments | null
  displayColor: THREE.Color
}

const HOVER_EMISSIVE = new THREE.Color('#38bdf8')
const EDGE_LIMIT = 4000 // above this many meshes, skip edge overlays to keep the frame rate up

/**
 * Thin wrapper around a Three.js scene that knows about IFC elements by GlobalId.
 * It owns the render loop, picking, per-element colouring and visibility.
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
  private grid: THREE.GridHelper | null = null
  private selectedId: string | null = null
  private hoveredId: string | null = null
  private pointerDirty = false
  private pointerDownAt = { x: 0, y: 0 }
  private disposed = false

  private readonly container: HTMLElement
  private readonly callbacks: ViewerCallbacks

  constructor(container: HTMLElement, callbacks: ViewerCallbacks = {}) {
    this.container = container
    this.callbacks = callbacks
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    this.renderer.domElement.style.display = 'block'
    this.renderer.domElement.style.touchAction = 'none'
    container.appendChild(this.renderer.domElement)

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.05, 5000)
    this.camera.position.set(20, 15, 20)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI * 0.95

    const hemisphere = new THREE.HemisphereLight(0xffffff, 0x334155, 1.1)
    const key = new THREE.DirectionalLight(0xffffff, 1.7)
    key.position.set(30, 50, 20)
    const fill = new THREE.DirectionalLight(0xbfdbfe, 0.5)
    fill.position.set(-30, 20, -20)
    this.scene.add(hemisphere, key, fill, this.root)

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(container)
    this.resize()

    const canvas = this.renderer.domElement
    canvas.addEventListener('pointermove', this.onPointerMove)
    canvas.addEventListener('pointerdown', this.onPointerDown)
    canvas.addEventListener('pointerup', this.onPointerUp)
    canvas.addEventListener('pointerleave', this.onPointerLeave)

    this.renderer.setAnimationLoop(this.frame)
  }

  // -- loading ------------------------------------------------------------------------

  async load(url: string): Promise<{ meshCount: number }> {
    this.clear()
    const gltf = await new GLTFLoader().loadAsync(url)
    const meshes: THREE.Mesh[] = []
    gltf.scene.traverse((object) => {
      if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh)
    })
    const withEdges = meshes.length <= EDGE_LIMIT

    for (const mesh of meshes) {
      const source = mesh.material as THREE.MeshStandardMaterial
      const material = new THREE.MeshStandardMaterial({
        color: source.color?.clone() ?? new THREE.Color('#cbd5e1'),
        opacity: source.opacity ?? 1,
        transparent: (source.opacity ?? 1) < 1,
        roughness: 0.85,
        metalness: 0,
        side: THREE.DoubleSide,
        polygonOffset: withEdges,
        polygonOffsetFactor: 1,
        polygonOffsetUnits: 1,
      })
      mesh.material = material
      mesh.matrixAutoUpdate = false
      mesh.updateMatrix()

      let edges: THREE.LineSegments | null = null
      if (withEdges) {
        edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(mesh.geometry, 20),
          new THREE.LineBasicMaterial({ color: 0x0b1220, transparent: true, opacity: 0.45 }),
        )
        edges.matrix.copy(mesh.matrix)
        edges.matrixAutoUpdate = false
        edges.raycast = () => undefined
        this.root.add(edges)
      }

      this.root.add(mesh)
      this.entries.set(mesh.name, { mesh, material, edges, displayColor: material.color.clone() })
    }

    this.addGrid()
    this.fitToView()
    return { meshCount: meshes.length }
  }

  clear(): void {
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
    if (this.grid) {
      this.scene.remove(this.grid)
      this.grid.geometry.dispose()
      ;(this.grid.material as THREE.Material).dispose()
      this.grid = null
    }
    this.selectedId = null
    this.hoveredId = null
  }

  // -- appearance ------------------------------------------------------------------------

  /** Recolour every element. `resolve` returns a CSS hex colour or null to keep the current one. */
  applyColors(resolve: (globalId: string) => string | null): void {
    for (const [id, entry] of this.entries) {
      const hex = resolve(id)
      if (hex) entry.displayColor.set(hex)
      this.paint(id, entry)
    }
  }

  setVisibility(isVisible: (globalId: string) => boolean): void {
    for (const [id, entry] of this.entries) {
      const visible = isVisible(id)
      entry.mesh.visible = visible
      if (entry.edges) entry.edges.visible = visible
    }
    if (this.hoveredId && !this.entries.get(this.hoveredId)?.mesh.visible) this.setHovered(null)
  }

  setSelected(globalId: string | null): void {
    const previous = this.selectedId
    this.selectedId = globalId
    if (previous) this.repaint(previous)
    if (globalId) this.repaint(globalId)
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
    const isSelected = id === this.selectedId
    const isHovered = id === this.hoveredId
    if (isSelected) {
      entry.material.color.set(SELECTION_COLOR)
      entry.material.emissive.set(SELECTION_COLOR)
      entry.material.emissiveIntensity = 0.35
    } else {
      entry.material.color.copy(entry.displayColor)
      entry.material.emissive.copy(isHovered ? HOVER_EMISSIVE : new THREE.Color(0x000000))
      entry.material.emissiveIntensity = isHovered ? 0.25 : 0
    }
  }

  // -- camera -------------------------------------------------------------------------------

  fitToView(globalIds?: string[]): void {
    const box = new THREE.Box3()
    const targets = globalIds
      ? globalIds.map((id) => this.entries.get(id)?.mesh).filter((m): m is THREE.Mesh => !!m)
      : [...this.entries.values()].filter((e) => e.mesh.visible).map((e) => e.mesh)
    for (const mesh of targets) box.expandByObject(mesh)
    if (box.isEmpty()) return

    const center = box.getCenter(new THREE.Vector3())
    const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.5)
    const distance = (radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2))) * 1.05
    const direction = new THREE.Vector3(1, 0.75, 1).normalize()
    this.camera.position.copy(center).addScaledVector(direction, distance)
    this.camera.near = Math.max(distance / 1000, 0.01)
    this.camera.far = distance * 50
    this.camera.updateProjectionMatrix()
    this.controls.target.copy(center)
    this.controls.update()
  }

  private addGrid(): void {
    const box = new THREE.Box3().setFromObject(this.root)
    if (box.isEmpty()) return
    const size = Math.ceil(Math.max(box.getSize(new THREE.Vector3()).x, box.getSize(new THREE.Vector3()).z) * 2.5)
    const divisions = Math.max(10, Math.min(120, Math.round(size)))
    this.grid = new THREE.GridHelper(size, divisions, 0x263349, 0x1a2538)
    const center = box.getCenter(new THREE.Vector3())
    this.grid.position.set(center.x, box.min.y - 0.02, center.z)
    ;(this.grid.material as THREE.Material).transparent = true
    ;(this.grid.material as THREE.Material).opacity = 0.7
    this.scene.add(this.grid)
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

  private onPointerLeave = (): void => {
    this.pointer.set(2, 2)
    this.setHovered(null)
    this.callbacks.onHover?.({ globalId: null, clientX: 0, clientY: 0 })
  }

  private pick(): string | null {
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const meshes = [...this.entries.values()].filter((e) => e.mesh.visible).map((e) => e.mesh)
    const hit = this.raycaster.intersectObjects(meshes, false)[0]
    return hit ? hit.object.name : null
  }

  private frame = (): void => {
    if (this.disposed) return
    if (this.pointerDirty) {
      this.pointerDirty = false
      const hit = this.pick()
      if (hit !== this.hoveredId) {
        this.setHovered(hit)
        this.callbacks.onHover?.({ globalId: hit, ...this.lastPointer })
      }
    }
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  private resize(): void {
    const { clientWidth, clientHeight } = this.container
    if (clientWidth === 0 || clientHeight === 0) return
    this.renderer.setSize(clientWidth, clientHeight, false)
    this.camera.aspect = clientWidth / clientHeight
    this.camera.updateProjectionMatrix()
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
    this.clear()
    this.controls.dispose()
    this.renderer.dispose()
    canvas.remove()
  }
}
