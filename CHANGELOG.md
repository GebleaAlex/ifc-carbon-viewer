# Changelog

## Unreleased

### Fixed

- **Utility classes on buttons, pills and chips were ignored.** The component classes (`.btn`, `.tool`, `.pill`, `.chip`, …) were unlayered CSS, which always beats Tailwind utilities. The keyboard button never hid on phones, warning chips were not yellow, compact buttons were not compact. They now live in the components layer.
- **A tooltip stayed stuck in the 3D view** after hovering or clicking a row in the Elements list. Hovering a row now highlights that element in the model instead, and the tooltip only follows the pointer inside the view. Near the right and bottom edges it flips instead of being cut off.
- **Fast clicks could show the wrong data.** Selecting two elements, or switching between two models, in quick succession let the slower response win: properties of another element, or two models drawn on top of each other.
- **Escape did too much.** Closing a dropdown, the storey/class popover, the export menu or a confirmation also cleared the focus or the selection behind it. Shortcuts no longer fire while a confirmation is open.
- **Failed uploads could not be removed**, and deleting a model while it was still being parsed brought it back. Deleting now reports errors instead of failing silently.
- **Screenshots had a transparent background**; they are now exported on the same dark backdrop as the view.
- The "only" action in the storey list was hover-only, so unreachable on touch screens. Dropdowns and popovers no longer hang off narrow screens.
- Copying a link no longer claims success when the browser refuses clipboard access.

### Added

- Double-click an element to zoom to it; double-click empty space to fit the model.
- Hide the side panel (`P`) to give the 3D view the whole window.
- The selection actions and the section slider are shown together, and no longer overlap the legend.
- A retry screen when the API cannot be reached, instead of an empty viewer.
- The browser tab shows the name of the open model.
- Tabs can be changed with the arrow keys.

### Changed

- The 3D view only renders when something changes, so an idle page no longer keeps the GPU busy.
- Moving the section plane no longer invalidates every material on each step.
- More compact header and toolbars on phones.

## 0.2.0

### Fixed

- **Volumes in millimetre models were close to zero.** Quantities were scaled by the length unit cubed instead of the file's volume unit, and the tessellated geometry (already in metres) was scaled a second time. A typical Revit or ArchiCAD export (millimetre lengths, cubic-metre volumes) therefore showed almost no carbon. Lengths, areas and volumes now each use their own unit. SI prefixes are applied per dimension, so a volume unit in cubic millimetres is 1e-9 m³, not 1e-3.
- **Keyword matching had false positives.** "Pipe" matched the IPE steel keyword, "heating" matched HEA, "steps" matched EPS. Keywords now match whole words only, and the most specific keyword wins ("glass wool" is insulation, not glass).
- **Assemblies were counted twice.** A curtain wall and its plates, or a stair and its flights, could both carry carbon. Assemblies now carry none themselves, and their parts find their storey through the assembly.
- **The 3D view was cropped on high-DPI screens.** The canvas took its size in device pixels, so on phones and Retina displays the model appeared off-centre and cut off.

### Added

- Material layers: layer sets are split by thickness, including air gaps; constituent sets by fraction; profile sets and lists are read too. Each element lists its layers with volume, mass and carbon.
- Floor area from spaces, slab quantities or slab geometry, and the kgCO₂e/m² intensity.
- Per-model material mapping (`GET`/`PUT /api/models/{id}/mapping`, `GET /api/models/{id}/materials`). The estimate is recomputed on the server without parsing the IFC again.
- CSV and JSON exports. The CSV has one row per layer and adds up to the model total.
- Six new factor categories: foam insulation, ceramic tiles, plastics, copper, mortar & screed, gravel & aggregate. Romanian and German keywords.
- Viewer:
  - colour by storey, see-through glass;
  - focus from charts, the legend or data-quality chips;
  - section cut, X-ray, isolate and hide;
  - camera presets, soft shadows, PNG screenshot.
- Overview tab: donut by material, carbon by storey and material, data-quality checks, floor area and intensity.
- Materials tab; selection panel with the layer breakdown, the calculation for each layer, and parent/part navigation.
- Deep links (`?model`, `element`, `color`, `tab`, `section`), keyboard shortcuts, upload progress, themed dropdowns and dialogs, paging for long element lists.
- A richer sample building in millimetres: three storeys, layered walls and slabs, windows in openings, a steel frame, a curtain wall, a stair, a roof assembly, spaces and one unknown material.
- `/api/health` reports the version. Models parsed by 0.1 are parsed again on start-up.

## 0.1.0

First release: IFC parsing with IfcOpenShell, GLB export, element-level carbon estimate, and a Vue/Three.js viewer with colour modes, storey and class filters, and property sets.
