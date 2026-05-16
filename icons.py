"""
ICONS — set HYSYS-style de 126 íconos SVG (viewBox 24×24).

Categorías: file, edit, view, sim, equip, stream, config, analysis,
workbook, nav, help, actions.

Uso:
    from icons import make_qicon
    icon = make_qicon("file-new", color="#1a1a1a", size=20)
    action.setIcon(icon)

Stroke siempre via currentColor → color parametrizable al renderizar.
"""

from typing import Optional

# id → (display_name, category, svg_paths)
ICONS = {
    'file-new': ('New', 'file', '<path d="M7 3h8l4 4v14H7V3z"/>\n    <path d="M15 3v4h4"/>\n    <path d="M13 12v6M10 15h6"/>'),
    'file-open': ('Open', 'file', '<path d="M3 7h6l2 2h10v10H3V7z"/>\n    <path d="M3 7V5h6l2 2"/>'),
    'file-save': ('Save', 'file', '<path d="M4 4h12l4 4v12H4V4z"/>\n    <path d="M7 4v6h9V4"/>\n    <path d="M7 14h10v6H7v-6z"/>\n    <path d="M13 6v3"/>'),
    'file-save-as': ('Save As', 'file', '<path d="M4 4h11l4 4v8"/>\n    <path d="M4 4v16h9"/>\n    <path d="M7 4v6h8"/>\n    <path d="M15 19l4-4 2 2-4 4h-2v-2z"/>'),
    'file-print': ('Print', 'file', '<path d="M7 3h10v6H7V3z"/>\n    <path d="M5 9h14v8h-2"/>\n    <path d="M5 17H3V9"/>\n    <path d="M7 13h10v8H7v-8z"/>\n    <path d="M16 12h1"/>'),
    'file-export': ('Export', 'file', '<path d="M14 3H6v18h12V11"/>\n    <path d="M14 3v5h5"/>\n    <path d="M11 14h10M17 10l4 4-4 4"/>'),
    'file-import': ('Import', 'file', '<path d="M18 3H10v18h12V11"/>\n    <path d="M18 3v5h4"/>\n    <path d="M2 14h11M6 10l-4 4 4 4"/>'),
    'file-close': ('Close', 'file', '<path d="M7 3h8l4 4v14H7V3z"/>\n    <path d="M15 3v4h4"/>\n    <path d="M11 12l4 4M15 12l-4 4"/>'),
    'file-recent': ('Recent', 'file', '<path d="M7 3h8l4 4v14H7V3z"/>\n    <path d="M15 3v4h4"/>\n    <circle cx="13" cy="15" r="3"/>\n    <path d="M13 13.5V15l1 1"/>'),
    'file-attach': ('Attach', 'file', '<path d="M16 7l-7 7a3 3 0 1 0 4 4l7-7a5 5 0 1 0-7-7L6 11"/>'),
    'edit-undo': ('Undo', 'edit', '<path d="M9 14l-5-5 5-5"/>\n    <path d="M4 9h10a6 6 0 0 1 6 6v0a6 6 0 0 1-6 6H8"/>'),
    'edit-redo': ('Redo', 'edit', '<path d="M15 14l5-5-5-5"/>\n    <path d="M20 9H10a6 6 0 0 0-6 6v0a6 6 0 0 0 6 6h6"/>'),
    'edit-copy': ('Copy', 'edit', '<path d="M9 9h11v11H9V9z"/>\n    <path d="M5 15V4h11v3"/>'),
    'edit-paste': ('Paste', 'edit', '<path d="M9 4h6v3H9V4z"/>\n    <path d="M9 5H5v16h14V5h-4"/>\n    <path d="M9 12h6M9 16h4"/>'),
    'edit-cut': ('Cut', 'edit', '<circle cx="6" cy="18" r="3"/>\n    <circle cx="18" cy="18" r="3"/>\n    <path d="M8 16L20 4M16 16L4 4"/>'),
    'edit-delete': ('Delete', 'edit', '<path d="M4 7h16"/>\n    <path d="M9 7V4h6v3"/>\n    <path d="M6 7l1 14h10l1-14"/>\n    <path d="M10 11v6M14 11v6"/>'),
    'edit-find': ('Find', 'edit', '<circle cx="11" cy="11" r="6"/>\n    <path d="M15.5 15.5L21 21"/>'),
    'edit-replace': ('Find & Replace', 'edit', '<circle cx="10" cy="10" r="5"/>\n    <path d="M13.5 13.5L18 18"/>\n    <path d="M14 20h6M18 18l2 2-2 2"/>'),
    'edit-select-all': ('Select All', 'edit', '<path d="M4 4h2M4 10v-2M4 14v-2M4 20v-2M10 4h-2M14 4h-2M20 4h-2M20 10v-2M20 14v-2M20 20v-2M10 20h-2M14 20h-2"/>\n    <path d="M8 8h8v8H8V8z"/>'),
    'edit-clone': ('Clone', 'edit', '<path d="M4 4h11v11H4V4z"/>\n    <path d="M9 9h11v11H9V9z"/>'),
    'zoom-in': ('Zoom In', 'view', '<circle cx="11" cy="11" r="6"/>\n    <path d="M15.5 15.5L21 21"/>\n    <path d="M11 8v6M8 11h6"/>'),
    'zoom-out': ('Zoom Out', 'view', '<circle cx="11" cy="11" r="6"/>\n    <path d="M15.5 15.5L21 21"/>\n    <path d="M8 11h6"/>'),
    'zoom-fit': ('Fit to Window', 'view', '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>\n    <path d="M9 9h6v6H9V9z"/>'),
    'zoom-100': ('Actual Size', 'view', '<circle cx="10" cy="10" r="6"/>\n    <path d="M14.5 14.5L20 20"/>\n    <path d="M9 8v4M11 12v-4"/>'),
    'zoom-selection': ('Zoom Selection', 'view', '<path d="M4 4h6v6H4V4z"/>\n    <path d="M14 14h6v6h-6v-6z"/>\n    <path d="M10 10l4 4"/>'),
    'pan': ('Pan', 'view', '<path d="M9 11V5a1.5 1.5 0 0 1 3 0v6"/>\n    <path d="M12 11V4.5a1.5 1.5 0 0 1 3 0V11"/>\n    <path d="M15 11V6a1.5 1.5 0 0 1 3 0v8c0 4-3 7-7 7-3 0-5-2-6-4l-3-6a1.5 1.5 0 0 1 2.5-1.5L6 13V8a1.5 1.5 0 0 1 3 0v3"/>'),
    'fullscreen': ('Fullscreen', 'view', '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
    'fullscreen-exit': ('Exit Fullscreen', 'view', '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>'),
    'grid': ('Grid', 'view', '<path d="M4 4h16v16H4V4z"/>\n    <path d="M4 9.3h16M4 14.6h16M9.3 4v16M14.6 4v16"/>'),
    'grid-snap': ('Snap to Grid', 'view', '<path d="M4 4h16v16H4V4z"/>\n    <path d="M4 9.3h16M4 14.6h16M9.3 4v16M14.6 4v16"/>\n    <circle cx="14.6" cy="9.3" r="1.5" fill="currentColor" stroke="none"/>'),
    'layers': ('Layers', 'view', '<path d="M12 3l9 5-9 5-9-5 9-5z"/>\n    <path d="M3 13l9 5 9-5"/>\n    <path d="M3 17l9 5 9-5"/>'),
    'ruler': ('Ruler / Measure', 'view', '<path d="M3 10l7-7 11 11-7 7L3 10z"/>\n    <path d="M7 6l2 2M10 9l1.5 1.5M13 6l2 2M14 11l1.5 1.5M17 8l2 2"/>'),
    'show-labels': ('Show Labels', 'view', '<path d="M4 5h7v6H4V5z"/>\n    <path d="M4 13h12v6H4v-6z"/>\n    <path d="M14 7h6M14 9h4"/>'),
    'hide': ('Hide', 'view', '<path d="M3 12s3-7 9-7 9 7 9 7-3 7-9 7-9-7-9-7z"/>\n    <circle cx="12" cy="12" r="3"/>\n    <path d="M4 4l16 16"/>'),
    'show': ('Show', 'view', '<path d="M3 12s3-7 9-7 9 7 9 7-3 7-9 7-9-7-9-7z"/>\n    <circle cx="12" cy="12" r="3"/>'),
    'sim-run': ('Run', 'sim', '<path d="M6 4l14 8-14 8V4z"/>'),
    'sim-pause': ('Pause / Hold', 'sim', '<path d="M7 4h3v16H7V4zM14 4h3v16h-3V4z"/>'),
    'sim-stop': ('Stop', 'sim', '<path d="M5 5h14v14H5V5z"/>'),
    'sim-step': ('Step', 'sim', '<path d="M5 4l10 8-10 8V4z"/>\n    <path d="M17 4v16"/>'),
    'sim-step-back': ('Step Back', 'sim', '<path d="M19 4L9 12l10 8V4z"/>\n    <path d="M7 4v16"/>'),
    'sim-reset': ('Reset', 'sim', '<path d="M4 12a8 8 0 1 1 2.5 5.8"/>\n    <path d="M4 6v5h5"/>'),
    'sim-converge': ('Converge', 'sim', '<circle cx="12" cy="12" r="8"/>\n    <circle cx="12" cy="12" r="4"/>\n    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/>'),
    'sim-active': ('Active', 'sim', '<circle cx="12" cy="12" r="9"/>\n    <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>'),
    'sim-hold': ('Hold', 'sim', '<path d="M7 4h3v16H7V4zM14 4h3v16h-3V4z"/>\n    <path d="M3 12h2M19 12h2"/>'),
    'sim-refresh': ('Refresh / Solve', 'sim', '<path d="M20 12a8 8 0 1 1-2.5-5.8"/>\n    <path d="M20 4v5h-5"/>'),
    'sim-converged-ok': ('Solved', 'sim', '<circle cx="12" cy="12" r="9"/>\n    <path d="M8 12l3 3 5-6"/>'),
    'sim-not-converged': ('Not Converged', 'sim', '<circle cx="12" cy="12" r="9"/>\n    <path d="M12 7v6M12 16v.5"/>'),
    'eq-cstr': ('CSTR Reactor', 'equip', '<circle cx="12" cy="12" r="7"/>\n    <path d="M9 9l6 6M15 9l-6 6"/>\n    <path d="M3 12h2M19 12h2M12 3v2M12 19v2"/>'),
    'eq-pfr': ('PFR / Plug Flow', 'equip', '<path d="M3 8h14a4 4 0 0 1 0 8H3"/>\n    <path d="M3 8v8"/>\n    <path d="M6 12h3M11 12h3M16 12h2"/>'),
    'eq-column': ('Distillation Column', 'equip', '<path d="M9 3h6v18H9V3z"/>\n    <path d="M9 7h6M9 10h6M9 13h6M9 16h6"/>\n    <path d="M15 5h4M5 19h4"/>'),
    'eq-hx': ('Heat Exchanger', 'equip', '<rect x="3" y="8" width="18" height="8" rx="1"/>\n    <path d="M3 12h18"/>\n    <path d="M7 8v-3M7 19v-3M17 8v-3M17 19v-3"/>'),
    'eq-hx-coil': ('Heat Exchanger (coil)', 'equip', '<rect x="3" y="6" width="18" height="12" rx="1"/>\n    <path d="M5 9c2 0 2 6 4 6s2-6 4-6 2 6 4 6 2-6 4-6"/>'),
    'eq-pump': ('Pump', 'equip', '<circle cx="12" cy="12" r="7"/>\n    <path d="M9 8l7 4-7 4V8z"/>\n    <path d="M3 12h2M19 12h2"/>'),
    'eq-compressor': ('Compressor', 'equip', '<path d="M4 5l16 5v4L4 19V5z"/>\n    <path d="M4 9v6"/>\n    <path d="M20 10v4"/>'),
    'eq-expander': ('Expander / Turbine', 'equip', '<path d="M20 5L4 10v4l16 5V5z"/>\n    <path d="M20 9v6"/>\n    <path d="M4 10v4"/>'),
    'eq-valve': ('Valve', 'equip', '<path d="M4 7v10l8-5-8-5z"/>\n    <path d="M20 7v10l-8-5 8-5z"/>\n    <path d="M12 7v-3M10 4h4"/>'),
    'eq-valve-control': ('Control Valve', 'equip', '<path d="M4 9v6l8-3-8-3z"/>\n    <path d="M20 9v6l-8-3 8-3z"/>\n    <path d="M12 9V6"/>\n    <circle cx="12" cy="5" r="2"/>'),
    'eq-separator-v': ('Vertical Separator', 'equip', '<path d="M9 3h6v18H9V3z" />\n    <path d="M9 4a3 3 0 0 1 6 0M9 20a3 3 0 0 0 6 0"/>\n    <path d="M9 11h6"/>'),
    'eq-separator-h': ('Horizontal Separator', 'equip', '<path d="M3 9h18v6H3V9z"/>\n    <path d="M3 12a3 3 0 0 1 0-6M21 12a3 3 0 0 0 0 6M3 12a3 3 0 0 0 0 6M21 12a3 3 0 0 1 0-6"/>\n    <path d="M6 13h12"/>'),
    'eq-tank': ('Tank', 'equip', '<path d="M5 6h14v14H5V6z"/>\n    <path d="M5 6a7 2 0 0 1 14 0"/>\n    <path d="M5 14h14"/>'),
    'eq-tank-cyl': ('Vertical Vessel', 'equip', '<path d="M6 5h12v14H6V5z"/>\n    <ellipse cx="12" cy="5" rx="6" ry="2"/>\n    <ellipse cx="12" cy="19" rx="6" ry="2"/>'),
    'eq-mixer': ('Mixer', 'equip', '<path d="M3 6l10 6-10 6V6z"/>\n    <path d="M3 6l10 6"/>\n    <path d="M13 12h8"/>'),
    'eq-tee': ('Tee / Splitter', 'equip', '<path d="M21 6L11 12l10 6V6z"/>\n    <path d="M11 12H3"/>'),
    'eq-heater': ('Heater', 'equip', '<circle cx="12" cy="12" r="7"/>\n    <path d="M10 9v6M14 9v6M10 12h4"/>\n    <path d="M3 12h2M19 12h2"/>'),
    'eq-cooler': ('Cooler', 'equip', '<circle cx="12" cy="12" r="7"/>\n    <path d="M9 9l6 6M15 9l-6 6M12 8v8M8 12h8"/>'),
    'eq-pipe': ('Pipe Segment', 'equip', '<path d="M3 9h18v6H3V9z"/>\n    <path d="M7 9v6M17 9v6"/>'),
    'eq-flare': ('Flare', 'equip', '<path d="M10 21h4V11h-4v10z"/>\n    <path d="M12 11c0-3-2-4-2-7 0 0 4 2 4 5 1-2 2-3 2-3s2 5-1 8"/>'),
    'stream-material': ('Material Stream', 'stream', '<path d="M3 12h14"/>\n    <path d="M14 8l5 4-5 4"/>'),
    'stream-energy': ('Energy Stream', 'stream', '<path d="M3 12h2M7 12h2M11 12h2M15 12h2"/>\n    <path d="M14 8l5 4-5 4"/>'),
    'stream-recycle': ('Recycle', 'stream', '<path d="M7 7l-3 3 3 3"/>\n    <path d="M4 10h11a5 5 0 0 1 5 5v0a5 5 0 0 1-5 5H9"/>'),
    'stream-adjust': ('Adjust', 'stream', '<circle cx="12" cy="12" r="8"/>\n    <path d="M12 4v4M12 16v4M4 12h4M16 12h4"/>\n    <circle cx="12" cy="12" r="2"/>'),
    'stream-set': ('Set', 'stream', '<path d="M5 6h14M5 12h14M5 18h14"/>\n    <circle cx="8" cy="6" r="2" fill="currentColor" stroke="none"/>\n    <circle cx="16" cy="12" r="2" fill="currentColor" stroke="none"/>\n    <circle cx="10" cy="18" r="2" fill="currentColor" stroke="none"/>'),
    'stream-balance': ('Balance', 'stream', '<path d="M12 4v16M5 8h14"/>\n    <path d="M5 8l-2 5a3 3 0 0 0 6 0L7 8M19 8l-2 5a3 3 0 0 0 6 0L21 8"/>'),
    'cfg-settings': ('Settings', 'config', '<circle cx="12" cy="12" r="3"/>\n    <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>'),
    'cfg-properties': ('Properties', 'config', '<path d="M4 5h16v14H4V5z"/>\n    <path d="M4 9h16"/>\n    <path d="M7 13h3M7 16h6"/>\n    <path d="M13 12h6v5h-6v-5z"/>'),
    'cfg-units': ('Units', 'config', '<path d="M3 14l11-11 7 7-11 11-7-7z"/>\n    <path d="M6 11l1.5 1.5M9 8l1.5 1.5M12 5l1.5 1.5M8 13l3 3"/>'),
    'cfg-fluid-pkg': ('Fluid Package', 'config', '<path d="M9 3h6v5l4 10a2 2 0 0 1-2 3H7a2 2 0 0 1-2-3l4-10V3z"/>\n    <path d="M9 3h6"/>\n    <path d="M7 14h10"/>'),
    'cfg-components': ('Components', 'config', '<circle cx="6" cy="7" r="2.5"/>\n    <circle cx="18" cy="7" r="2.5"/>\n    <circle cx="12" cy="17" r="2.5"/>\n    <path d="M8 8l4 7M16 8l-4 7M8 7h8"/>'),
    'cfg-rxn': ('Reactions', 'config', '<path d="M4 8h10M14 5l3 3-3 3"/>\n    <path d="M20 16H10M10 19l-3-3 3-3"/>'),
    'cfg-prefs': ('Preferences', 'config', '<path d="M4 6h10M4 12h6M4 18h12"/>\n    <circle cx="17" cy="6" r="2"/>\n    <circle cx="13" cy="12" r="2"/>\n    <circle cx="19" cy="18" r="2"/>'),
    'cfg-units-system': ('Unit System', 'config', '<path d="M4 4h16v16H4V4z"/>\n    <path d="M4 10h16M10 4v16"/>\n    <path d="M6 7h2M6 13h2M13 7h2M13 13h2M13 17h2"/>'),
    'an-case-study': ('Case Study', 'analysis', '<circle cx="5" cy="6" r="2"/>\n    <circle cx="5" cy="18" r="2"/>\n    <circle cx="19" cy="12" r="2"/>\n    <path d="M7 6h6l4 5M7 18h6l4-5"/>'),
    'an-optimizer': ('Optimizer', 'analysis', '<path d="M3 20L8 14l4 3 8-11"/>\n    <path d="M15 6h5v5"/>\n    <circle cx="20" cy="6" r="1.5" fill="currentColor" stroke="none"/>'),
    'an-sensitivity': ('Sensitivity', 'analysis', '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>'),
    'an-data-fit': ('Data Fit', 'analysis', '<path d="M3 20L21 6"/>\n    <circle cx="6" cy="17" r="1.5"/>\n    <circle cx="10" cy="15" r="1.5"/>\n    <circle cx="14" cy="10" r="1.5"/>\n    <circle cx="18" cy="8" r="1.5"/>'),
    'an-target': ('Spec / Target', 'analysis', '<circle cx="12" cy="12" r="8"/>\n    <circle cx="12" cy="12" r="4"/>\n    <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>'),
    'an-monte-carlo': ('Monte Carlo', 'analysis', '<path d="M4 7h6v6H4V7z"/>\n    <path d="M14 11h6v6h-6v-6z"/>\n    <circle cx="7" cy="10" r="1" fill="currentColor" stroke="none"/>\n    <circle cx="17" cy="14" r="1" fill="currentColor" stroke="none"/>\n    <circle cx="15.5" cy="15.5" r="1" fill="currentColor" stroke="none"/>'),
    'an-pinch': ('Pinch Analysis', 'analysis', '<path d="M3 6l9 6-9 6"/>\n    <path d="M21 6l-9 6 9 6"/>'),
    'wb-spreadsheet': ('Workbook', 'workbook', '<path d="M4 4h16v16H4V4z"/>\n    <path d="M4 9h16M4 14h16M9 4v16M15 4v16"/>'),
    'wb-table': ('Results Table', 'workbook', '<path d="M4 5h16v14H4V5z"/>\n    <path d="M4 9h16"/>\n    <path d="M9 9v10M15 9v10"/>'),
    'wb-plot': ('Plot', 'workbook', '<path d="M4 4v16h16"/>\n    <path d="M7 16l4-6 3 3 5-8"/>'),
    'wb-plot-xy': ('XY Plot', 'workbook', '<path d="M4 4v16h16"/>\n    <circle cx="8" cy="15" r="1.2"/>\n    <circle cx="11" cy="12" r="1.2"/>\n    <circle cx="14" cy="9" r="1.2"/>\n    <circle cx="17" cy="7" r="1.2"/>'),
    'wb-summary': ('Summary', 'workbook', '<path d="M5 4h14v16H5V4z"/>\n    <path d="M8 8h8M8 12h8M8 16h5"/>'),
    'wb-report': ('Report', 'workbook', '<path d="M7 3h8l4 4v14H7V3z"/>\n    <path d="M15 3v4h4"/>\n    <path d="M10 12h6M10 15h6M10 18h4"/>'),
    'wb-databook': ('Databook', 'workbook', '<path d="M5 5h14v15a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5z"/>\n    <path d="M5 5a2 2 0 0 1 2-2h11v2"/>\n    <path d="M9 9h7M9 12h7M9 15h5"/>'),
    'nav-pfd': ('PFD', 'nav', '<circle cx="6" cy="7" r="2.5"/>\n    <path d="M14 5h6v4h-6V5z"/>\n    <circle cx="17" cy="17" r="2.5"/>\n    <path d="M8.5 7H14M17 9v5.5M14 7l-7.5 9"/>'),
    'nav-tree': ('Tree View', 'nav', '<circle cx="5" cy="6" r="1.5"/>\n    <circle cx="5" cy="12" r="1.5"/>\n    <circle cx="5" cy="18" r="1.5"/>\n    <path d="M5 7v10"/>\n    <path d="M6 6h6M6 12h6M6 18h6"/>\n    <path d="M14 4h6v4h-6V4zM14 10h6v4h-6v-4zM14 16h6v4h-6v-4z"/>'),
    'nav-navigator': ('Navigator', 'nav', '<circle cx="12" cy="12" r="9"/>\n    <path d="M14.5 9.5l-2 5-5 2 2-5 5-2z"/>'),
    'nav-home': ('Home', 'nav', '<path d="M4 11l8-7 8 7v9H4v-9z"/>\n    <path d="M10 20v-6h4v6"/>'),
    'nav-back': ('Back', 'nav', '<path d="M14 6l-6 6 6 6"/>'),
    'nav-forward': ('Forward', 'nav', '<path d="M10 6l6 6-6 6"/>'),
    'nav-up': ('Up Level', 'nav', '<path d="M12 18V6M6 12l6-6 6 6"/>'),
    'nav-objects': ('Object Palette', 'nav', '<path d="M4 4h7v7H4V4z"/>\n    <path d="M13 4h7v7h-7V4z"/>\n    <path d="M4 13h7v7H4v-7z"/>\n    <path d="M13 13h7v7h-7v-7z"/>'),
    'help-help': ('Help', 'help', '<circle cx="12" cy="12" r="9"/>\n    <path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"/>\n    <path d="M12 17v.5"/>'),
    'help-info': ('Info', 'help', '<circle cx="12" cy="12" r="9"/>\n    <path d="M12 11v6M12 8v.5"/>'),
    'help-warning': ('Warning', 'help', '<path d="M12 3l10 18H2L12 3z"/>\n    <path d="M12 10v5M12 18v.5"/>'),
    'help-error': ('Error', 'help', '<circle cx="12" cy="12" r="9"/>\n    <path d="M8 8l8 8M16 8l-8 8"/>'),
    'help-success': ('Success', 'help', '<circle cx="12" cy="12" r="9"/>\n    <path d="M7 12l4 4 6-7"/>'),
    'help-question': ('Question', 'help', '<path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"/>\n    <path d="M12 17v.5"/>'),
    'help-bug': ('Debug', 'help', '<path d="M8 8a4 4 0 0 1 8 0v5a4 4 0 0 1-8 0V8z"/>\n    <path d="M8 11H4M16 11h4M8 7L5 5M16 7l3-2M8 14l-4 3M16 14l4 3M12 7V4"/>'),
    'help-lock': ('Locked', 'help', '<path d="M5 11h14v10H5V11z"/>\n    <path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
    'act-add': ('Add / Plus', 'actions', '<path d="M4 4h16v16H4V4z"/>\n    <path d="M12 8v8M8 12h8"/>'),
    'act-add-row': ('Add Row', 'actions', '<path d="M3 5h13v5H3V5z"/>\n    <path d="M3 13h13v5H3v-5z"/>\n    <path d="M20 14v6M17 17h6"/>'),
    'act-edit': ('Edit (pencil)', 'actions', '<path d="M3 21l4-1L19 8l-3-3L4 17l-1 4z"/>\n    <path d="M14 6l3 3"/>'),
    'act-edit-row': ('Edit Row', 'actions', '<path d="M3 5h11v5H3V5z"/>\n    <path d="M3 13h7v5H3v-5z"/>\n    <path d="M21 12l-7 7-3 1 1-3 7-7 2 2z"/>'),
    'act-remove-row': ('Remove Row', 'actions', '<path d="M3 5h13v5H3V5z"/>\n    <path d="M3 13h13v5H3v-5z"/>\n    <path d="M17 17h6"/>'),
    'act-clear': ('Clear All', 'actions', '<path d="M4 7h16"/>\n    <path d="M9 7V4h6v3"/>\n    <path d="M6 7l1 14h10l1-14"/>\n    <path d="M10 11l4 6M14 11l-4 6"/>'),
    'act-apply': ('Apply / Confirm', 'actions', '<path d="M4 12l5 5L20 6"/>'),
    'act-cancel': ('Cancel', 'actions', '<path d="M6 6l12 12M18 6L6 18"/>'),
    'act-money': ('Economic Analysis', 'actions', '<circle cx="12" cy="12" r="9"/>\n    <path d="M14 9c0-1-1-2-2-2s-3 .5-3 2 2 2 3 2 3 .5 3 2-1.5 2-3 2-3-.5-3-2"/>\n    <path d="M12 5v2M12 17v2"/>'),
    'act-connect': ('Connect Stream', 'actions', '<circle cx="5" cy="12" r="2"/>\n    <circle cx="19" cy="12" r="2"/>\n    <path d="M7 12h10"/>'),
    'act-waypoint': ('Insert Waypoint', 'actions', '<path d="M3 12h6M15 12h6"/>\n    <circle cx="12" cy="12" r="3"/>\n    <path d="M12 5v2M12 17v2"/>'),
    'act-examples': ('Examples / Templates', 'actions', '<path d="M5 5h6v6H5V5z"/>\n    <path d="M13 5h6v6h-6V5z"/>\n    <path d="M5 13h6v6H5v-6z"/>\n    <path d="M13 13h6v6h-6v-6z"/>\n    <path d="M9 8l1 1 2-2"/>'),
    'act-frame-pfd': ('Toggle PFD Frame', 'actions', '<path d="M3 3h18v18H3V3z"/>\n    <path d="M6 6h12v12H6V6z"/>\n    <path d="M14 18v3M18 14h3"/>'),
    'act-setpoint': ('Setpoint', 'actions', '<circle cx="12" cy="12" r="8"/>\n    <path d="M12 4v4M12 16v4M4 12h4M16 12h4"/>\n    <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/>'),
    'act-dof': ('DOF / Balance Check', 'actions', '<path d="M5 4h14v6H5V4z"/>\n    <path d="M5 14h14v6H5v-6z"/>\n    <path d="M8 7h8M8 17h5"/>\n    <path d="M16 16l2 2 3-3"/>'),
}

# Categorías para agrupar en pickers / pallets
CATEGORIES = ["file", "edit", "view", "sim", "actions", "equip",
              "stream", "workbook", "analysis", "nav", "config", "help"]


# Mapeo eq_type → icon_id del set HYSYS equip
# Conecta los nombres de equipment_costs.EQUIPMENT_DATA con los íconos
# 'equip' para mostrar en paneles, tooltips y diálogos.
EQ_TYPE_TO_ICON = {
    "Reactor — jacketed agitated":      "eq-cstr",
    "Reactor — jacketed non-agit.":     "eq-pfr",
    "Reactor — fluidized bed":          "eq-cstr",
    "Crystallizer":                     "eq-cstr",
    "Tower (column shell)":             "eq-column",
    "Heat exch. — floating head":       "eq-hx",
    "Heat exch. — air cooler":          "eq-cooler",
    "Heat exch. — kettle reboiler":     "eq-heater",
    "Heat exch. — fixed tube":          "eq-hx",
    "Heat exch. — U-tube":              "eq-hx",
    "Evaporator — vertical":            "eq-heater",
    "Fired heater — non-reformer":      "eq-heater",
    "Vessel — vertical":                "eq-separator-v",
    "Vessel — horizontal":              "eq-separator-h",
    "Storage tank — cone roof":         "eq-tank",
    "Storage tank — floating roof":     "eq-tank",
    "Pump — centrifugal":               "eq-pump",
    "Pump — positive displacement":     "eq-pump",
    "Compressor — centrifugal":         "eq-compressor",
    "Compressor — reciprocating":       "eq-compressor",
    "Fan":                              "eq-compressor",
    "Filter — belt":                    "eq-separator-h",
    "Filter — rotary drum":             "eq-separator-h",
    "Dryer — drum":                     "eq-tank-cyl",
    "Dryer — rotary":                   "eq-tank-cyl",
    "Mixer — static":                   "eq-mixer",
    "Mixer":                            "eq-mixer",
}


def icon_for_eq_type(eq_type: str) -> str:
    """Devuelve icon_id HYSYS para un eq_type. Fallback eq-mixer."""
    return EQ_TYPE_TO_ICON.get(eq_type, "eq-mixer")


def list_by_cat(cat: str):
    """Devuelve lista de (id, name) en una categoría."""
    return [(iid, ICONS[iid][0])
             for iid in ICONS
             if ICONS[iid][1] == cat]


def svg_string(icon_id: str, color: str = "#1a1a1a",
                stroke_width: float = 1.6) -> Optional[str]:
    """Devuelve el SVG completo como string, listo para QSvgRenderer.
    None si el icon_id no existe."""
    entry = ICONS.get(icon_id)
    if entry is None:
        return None
    _, _, paths = entry
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )


def make_qicon(icon_id: str, color: str = "#1a1a1a",
                size: int = 22, stroke_width: float = 1.6):
    """Renderiza el SVG del ícono a un QIcon de tamaño `size`×`size`.
    Devuelve None si el icon_id no existe.
    
    Lazy: importa Qt solo cuando se llama (módulo usable headless)."""
    svg = svg_string(icon_id, color, stroke_width)
    if svg is None:
        return None
    try:
        from PySide6.QtCore   import QByteArray, Qt
        from PySide6.QtGui    import QIcon, QPixmap, QPainter
        from PySide6.QtSvg    import QSvgRenderer
    except ImportError:
        return None
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return QIcon(px)