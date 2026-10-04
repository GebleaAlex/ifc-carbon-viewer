import type { CameraView, Viewer } from '../three/Viewer'

/**
 * The 3D view lives inside ViewerPanel, but the header (screenshot) and keyboard shortcuts
 * need it too. ViewerPanel registers its instance here; everyone else calls these helpers.
 */
let instance: Viewer | null = null

export function registerViewer(viewer: Viewer | null): void {
  instance = viewer
}

export const viewerBridge = {
  fit: (ids?: string[]) => instance?.fitToView(ids),
  setView: (view: CameraView) => instance?.setView(view),
  screenshot: (): string | null => instance?.screenshot() ?? null,
}
