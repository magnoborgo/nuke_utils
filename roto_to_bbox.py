"""
Roto Bounding Box Tool for Foundry Nuke
==========================================
Creates an animated Crop node driven by the per-frame world-space boundaries
of a selected RotoPaint / Roto shape.

This proof of concept was "coded" live with help of Claude and ChatGPT for this video https://www.youtube.com/watch?v=lPamGg187Ac

How transforms work (confirmed by debug inspection)
----------------------------------------------------
Nuke's rotopaint stores control points in a centered, Y-up coordinate space.
The AnimCTransform on each shape/layer carries an extra matrix
(getExtraMatrixAnimCurve) that encodes the full world-space mapping,
including the Y-flip and translation to pixel space.

The correct world-space point for a control point at (cx, cy) is:

    [x']   [extra_matrix 4x4]   [cx]
    [y'] =                    * [cy]
    [z']                        [0 ]
    [w']                        [1 ]

    pixel_x = x' / w'
    pixel_y = y' / w'

The shape/layer's TRS knobs (translation, rotation, scale, pivot, skewX)
are SEPARATE from the extra matrix — they describe user-applied transforms
ON TOP of it. These must be applied first (innermost), then the extra matrix.

Full chain per object:
    world_point = extra_matrix * TRS_matrix * local_point

Hierarchy:
    final = shape_extra * shape_TRS
          * layer1_extra * layer1_TRS   (immediate parent, then outward)
          * ...
          * layerN_extra * layerN_TRS

The root layer's extra matrix on the roto NODE itself is read via the
node's 'extra_matrix' knob (separate from the curves hierarchy).

Usage
-----
1. Select a single Roto or RotoPaint node.
2. Run from Script Editor, or register via register_menu().

Output
------
Creates either:
- an animated regular Crop,
- a static Crop covering the full travelled bbox area plus a helper Transform, or
- a Transform node stabilized by the bbox center followed by a static Crop,
  a post-crop Transform over black, plus an inverse matchmove Transform.

'crop' is OFF — acts as bbox carrier; enable to hard-crop.
Crop 'reformat' is ON for all generated Crop nodes.

Requirements: Nuke 15, nuke.rotopaint
"""

import nuke
import nuke.rotopaint as rp
import math


# ---------------------------------------------------------------------------
# 4x4 matrix — flat 16-element list, row-major
# ---------------------------------------------------------------------------

def _identity4():
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]

def _mat4_mul(A, B):
    """Multiply two 4x4 row-major matrices."""
    R = [0.0] * 16
    for row in range(4):
        for col in range(4):
            for k in range(4):
                R[row*4+col] += A[row*4+k] * B[k*4+col]
    return R

def _transform_point(M, x, y):
    """
    Apply 4x4 row-major matrix M to 2D point (x, y, 0, 1).
    Returns (x', y') after homogeneous divide.
    """
    xp = M[0]*x + M[1]*y + M[3]
    yp = M[4]*x + M[5]*y + M[7]
    wp = M[12]*x + M[13]*y + M[15]
    if wp == 0.0:
        wp = 1.0
    return xp / wp, yp / wp


# ---------------------------------------------------------------------------
# Read AnimCTransform into a 4x4 matrix
# ---------------------------------------------------------------------------

def _read_extra_matrix(transform, frame):
    """
    Read getExtraMatrixAnimCurve(row, col) for a 4x4 and return as a
    flat 16-element row-major list. Returns identity if unavailable.
    """
    M = _identity4()
    try:
        for row in range(4):
            for col in range(4):
                c = transform.getExtraMatrixAnimCurve(row, col)
                if c is not None:
                    M[row*4 + col] = c.evaluate(frame)
    except Exception:
        pass
    return M


def _read_trs_matrix(transform, frame):
    """
    Build a 4x4 TRS matrix from the AnimCTransform's individual
    translation / rotation / scale / pivot / skewX curves.

    Nuke's concatenation order (same as its Transform node):
        M = T(translate) * T(pivot) * R * Sk * S * T(-pivot)
    """

    def _cv(getter, idx, default):
        try:
            c = getter(idx)
            return c.evaluate(frame) if c is not None else default
        except Exception:
            return default

    tx  = _cv(transform.getTranslationAnimCurve, 0, 0.0)
    ty  = _cv(transform.getTranslationAnimCurve, 1, 0.0)
    rot = _cv(transform.getRotationAnimCurve,    0, 0.0)   # degrees
    sx  = _cv(transform.getScaleAnimCurve,       0, 1.0)
    sy  = _cv(transform.getScaleAnimCurve,       1, 1.0)
    px  = _cv(transform.getPivotPointAnimCurve,  0, 0.0)
    py  = _cv(transform.getPivotPointAnimCurve,  1, 0.0)
    skx = _cv(transform.getSkewXAnimCurve,       0, 0.0)   # degrees

    r   = math.radians(rot)
    sk  = math.radians(skx)
    cr, sr = math.cos(r), math.sin(r)
    tsk = math.tan(sk)

    # T(-pivot)
    Tnp = [1,0,0,-px,  0,1,0,-py,  0,0,1,0,  0,0,0,1]
    # S
    S   = [sx,0,0,0,  0,sy,0,0,  0,0,1,0,  0,0,0,1]
    # Skew X
    Sk  = [1,tsk,0,0,  0,1,0,0,  0,0,1,0,  0,0,0,1]
    # R
    R   = [cr,-sr,0,0,  sr,cr,0,0,  0,0,1,0,  0,0,0,1]
    # T(pivot)
    Tp  = [1,0,0,px,  0,1,0,py,  0,0,1,0,  0,0,0,1]
    # T(translate)
    Tt  = [1,0,0,tx,  0,1,0,ty,  0,0,1,0,  0,0,0,1]

    # Concatenate: Tt * Tp * R * Sk * S * Tnp
    M = _mat4_mul(Tnp, S)
    M = _mat4_mul(Sk, M)
    M = _mat4_mul(R,  M)
    M = _mat4_mul(Tp, M)
    M = _mat4_mul(Tt, M)
    return M


def _object_matrix(obj, frame):
    """
    Full matrix for one roto object (Shape or Layer):
        object_matrix = extra_matrix * TRS_matrix
    """
    t = obj.getTransform()
    extra = _read_extra_matrix(t, frame)
    trs   = _read_trs_matrix(t, frame)
    return _mat4_mul(extra, trs)


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------

def _get_ancestor_layers(item, roto_node):
    """
    Return ancestor Layer objects from immediate parent → outermost
    (just below root). Root itself excluded.
    """
    root = roto_node['curves'].rootLayer
    ancestors = []

    def _find(layer, target, path):
        for child in layer:
            cur = path + [layer]
            if child is target:
                ancestors.extend(cur[1:])  # skip root
                return True
            if isinstance(child, rp.Layer):
                if _find(child, target, cur):
                    return True
        return False

    _find(root, item, [])
    return ancestors


def _build_world_matrix(shape, roto_node, frame):
    """
    Accumulate the full world-space matrix for *shape* at *frame*.

        world = shape_matrix
              * parent_layer_matrix (innermost first, then outward)
              * ...

    The extra matrix already embedded in each object's transform
    handles the final pixel-space mapping, so no separate node-level
    extra_matrix pass is needed.
    """
    M = _object_matrix(shape, frame)

    for layer in _get_ancestor_layers(shape, roto_node):
        layer_M = _object_matrix(layer, frame)
        M = _mat4_mul(layer_M, M)

    return M


# ---------------------------------------------------------------------------
# Shape discovery
# ---------------------------------------------------------------------------

def _get_shape_names(roto_node):
    root = roto_node['curves'].rootLayer
    results = []

    def _walk(layer, prefix):
        for item in layer:
            if isinstance(item, rp.Shape):
                display = "{}/{}".format(prefix, item.name) if prefix else item.name
                results.append((display, item))
            elif isinstance(item, rp.Layer):
                _walk(item, "{}/{}".format(prefix, item.name) if prefix else item.name)

    _walk(root, "")
    return results


# ---------------------------------------------------------------------------
# Per-frame bbox
# ---------------------------------------------------------------------------

def _shape_bbox_at_frame(shape, roto_node, frame):
    """
    Return (x, y, r, t) world-space pixel bbox of *shape* at *frame*.
    """
    M = _build_world_matrix(shape, roto_node, frame)
    xs, ys = [], []

    for cp in shape:
        try:
            center = cp.center.getPosition(frame)
            cx, cy = center[0], center[1]
        except Exception:
            continue

        wx, wy = _transform_point(M, cx, cy)
        xs.append(wx)
        ys.append(wy)

        # Tangent handles — positions are absolute in the same space as center
        for attr in ("leftTangent", "rightTangent"):
            try:
                tang = getattr(cp, attr).getPosition(frame)
                tx, ty = _transform_point(M, tang[0], tang[1])
                xs.append(tx)
                ys.append(ty)
            except Exception:
                pass

    if not xs:
        return 0.0, 0.0, 0.0, 0.0

    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Crop mode helpers
# ---------------------------------------------------------------------------

CROP_MODE_REGULAR = "Regular crop"
CROP_MODE_STATIC = "Static crop"
CROP_MODE_STABILIZED = "Stabilized crop"
CROP_MODES = [CROP_MODE_REGULAR, CROP_MODE_STATIC, CROP_MODE_STABILIZED]


def _get_project_format_size():
    """Return the root format width/height as ints."""
    fmt = nuke.root().format()
    return int(fmt.width()), int(fmt.height())


def _parse_offset(value):
    """Parse user crop offset input. Empty input means 0."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return 0
    try:
        return int(round(float(value)))
    except Exception:
        nuke.message("Offset must be a number.")
        return None


def _int_box(x, y, r, t, offset=0, frame_width=None, frame_height=None):
    """
    Convert bbox values to integer Crop.box values, apply offset, and clamp
    the result to the project image frame.

    Positive offset expands the crop. Negative offset contracts it.
    """
    x = int(math.floor(x)) - offset
    y = int(math.floor(y)) - offset
    r = int(math.ceil(r)) + offset
    t = int(math.ceil(t)) + offset

    if frame_width is not None:
        x = max(0, min(int(frame_width), x))
        r = max(0, min(int(frame_width), r))
    if frame_height is not None:
        y = max(0, min(int(frame_height), y))
        t = max(0, min(int(frame_height), t))

    # Keep a valid box even with a large negative offset.
    if r < x:
        mid = int(round((x + r) * 0.5))
        x = r = mid
    if t < y:
        mid = int(round((y + t) * 0.5))
        y = t = mid

    return x, y, r, t


def _set_static_box(crop_node, box):
    """Set Crop.box as non-animated integer values."""
    knob = crop_node['box']
    try:
        knob.clearAnimated()
    except Exception:
        pass
    for i, value in enumerate(box):
        knob.setValue(int(value), i)


def _set_animated_box(crop_node, frame_boxes):
    """Set Crop.box as animated integer values."""
    knob = crop_node['box']
    knob.setAnimated()
    for frame, box in frame_boxes:
        for i, value in enumerate(box):
            knob.setValueAt(int(value), int(frame), i)


def _enable_crop_reformat(crop_node):
    """Turn on Crop.reformat when that knob exists."""
    if 'reformat' in crop_node.knobs():
        crop_node['reformat'].setValue(True)


def _set_transform_filter_impulse(transform_node):
    """Set Transform.filter to impulse when available."""
    if 'filter' in transform_node.knobs():
        try:
            transform_node['filter'].setValue('impulse')
        except Exception:
            # Some Nuke versions expose filter as an enum index.
            try:
                transform_node['filter'].setValue(0)
            except Exception:
                pass


def _set_transform_translate(transform_node, x_value, y_value, animated=False):
    """Set Transform.translate using float values, optionally clearing animation."""
    translate = transform_node['translate']
    if not animated:
        try:
            translate.clearAnimated()
        except Exception:
            pass
    translate.setValue(float(x_value), 0)
    translate.setValue(float(y_value), 1)


def _copy_translate_animation(source_transform, destination_transform):
    """Copy translate animation/static values from one Transform to another."""
    source_translate = source_transform['translate']
    destination_translate = destination_transform['translate']

    try:
        if source_translate.isAnimated():
            destination_translate.copyAnimations(source_translate.animations())
            return
    except Exception:
        pass

    try:
        destination_translate.setValue(float(source_translate.value(0)), 0)
        destination_translate.setValue(float(source_translate.value(1)), 1)
    except Exception:
        pass


def _create_static_crop_transform(crop_node, static_box, source_node):
    """Create a helper Transform for Static crop, using the Crop.box x/y values."""
    transform = nuke.createNode('Transform', inpanel=False)
    transform.setName('{}_Static_Transform'.format(crop_node.name()))
    transform.setInput(0, crop_node)
    transform['xpos'].setValue(crop_node['xpos'].value() + 150)
    transform['ypos'].setValue(crop_node['ypos'].value())
    transform['label'].setValue('static crop transform')
    _set_transform_translate(transform, int(static_box[0]), int(static_box[1]), animated=False)
    _set_transform_filter_impulse(transform)
    return transform


def _create_matchmove_transform(stabilize_transform, input_node):
    """Create an inverse copy of the stabilization Transform for matchmove."""
    matchmove = nuke.createNode('Transform', inpanel=False)
    matchmove.setName('{}_Matchmove'.format(stabilize_transform.name()))
    matchmove.setInput(0, input_node)
    matchmove['xpos'].setValue(input_node['xpos'].value() + 150)
    matchmove['ypos'].setValue(input_node['ypos'].value())
    matchmove['label'].setValue('matchmove')

    if 'center' in stabilize_transform.knobs() and 'center' in matchmove.knobs():
        try:
            matchmove['center'].setValue(float(stabilize_transform['center'].value(0)), 0)
            matchmove['center'].setValue(float(stabilize_transform['center'].value(1)), 1)
        except Exception:
            pass

    _copy_translate_animation(stabilize_transform, matchmove)

    if 'invert_matrix' in matchmove.knobs():
        matchmove['invert_matrix'].setValue(True)

    _set_transform_filter_impulse(matchmove)
    return matchmove


def _create_stabilized_post_crop_chain(crop_node, static_box):
    """
    Create the post-crop padding chain for Stabilized crop:
        Crop -> Transform -> Merge(A=Transform, B=black Constant)

    The Transform.translate uses the Crop.box x/y values and impulse filter.
    The Merge output is intended to feed the inverse matchmove Transform.
    """
    post_transform = nuke.createNode('Transform', inpanel=False)
    post_transform.setName('{}_PostCrop_Transform'.format(crop_node.name()))
    post_transform.setInput(0, crop_node)
    post_transform['xpos'].setValue(crop_node['xpos'].value() + 150)
    post_transform['ypos'].setValue(crop_node['ypos'].value())
    post_transform['label'].setValue('post stabilized crop transform')
    _set_transform_translate(post_transform, int(static_box[0]), int(static_box[1]), animated=False)
    _set_transform_filter_impulse(post_transform)

    constant = nuke.createNode('Constant', inpanel=False)
    constant.setName('{}_Black'.format(crop_node.name()))
    constant['xpos'].setValue(post_transform['xpos'].value())
    constant['ypos'].setValue(post_transform['ypos'].value() + 90)
    if 'color' in constant.knobs():
        try:
            constant['color'].setValue(0.0, 0)
            constant['color'].setValue(0.0, 1)
            constant['color'].setValue(0.0, 2)
            constant['color'].setValue(1.0, 3)
        except Exception:
            pass

    merge = nuke.createNode('Merge2', inpanel=False)
    merge.setName('{}_Over_Black'.format(crop_node.name()))
    merge['xpos'].setValue(post_transform['xpos'].value() + 150)
    merge['ypos'].setValue(post_transform['ypos'].value())
    if 'operation' in merge.knobs():
        try:
            merge['operation'].setValue('over')
        except Exception:
            pass

    # User-requested wiring: input A = Transform, input B = Constant.
    merge.setInput(0, post_transform)
    merge.setInput(1, constant)

    return post_transform, constant, merge


def _union_box(frame_boxes):
    """Return the static bbox that contains all frame bboxes."""
    xs = [box[0] for _, box in frame_boxes]
    ys = [box[1] for _, box in frame_boxes]
    rs = [box[2] for _, box in frame_boxes]
    ts = [box[3] for _, box in frame_boxes]
    return int(min(xs)), int(min(ys)), int(max(rs)), int(max(ts))


def _max_size_box_around_reference_center(frame_boxes, reference_frame=None, frame_width=None, frame_height=None):
    """
    Return a static box using the largest per-frame bbox width/height,
    centered on the bbox center at reference_frame.
    """
    if reference_frame is None:
        reference_frame = frame_boxes[0][0]

    ref_box = frame_boxes[0][1]
    for frame, box in frame_boxes:
        if frame == reference_frame:
            ref_box = box
            break

    cx = (ref_box[0] + ref_box[2]) * 0.5
    cy = (ref_box[1] + ref_box[3]) * 0.5
    max_w = max(box[2] - box[0] for _, box in frame_boxes)
    max_h = max(box[3] - box[1] for _, box in frame_boxes)

    x = int(math.floor(cx - max_w * 0.5))
    y = int(math.floor(cy - max_h * 0.5))
    r = int(math.ceil(cx + max_w * 0.5))
    t = int(math.ceil(cy + max_h * 0.5))

    if frame_width is not None:
        if x < 0:
            r -= x
            x = 0
        if r > frame_width:
            x -= (r - frame_width)
            r = frame_width
        x = max(0, int(x))
        r = min(int(frame_width), int(r))
    if frame_height is not None:
        if y < 0:
            t -= y
            y = 0
        if t > frame_height:
            y -= (t - frame_height)
            t = frame_height
        y = max(0, int(y))
        t = min(int(frame_height), int(t))

    return int(x), int(y), int(r), int(t)


def _frame_centers(frame_boxes):
    """Return [(frame, center_x, center_y), ...] from integer bboxes."""
    centers = []
    for frame, box in frame_boxes:
        centers.append((frame, (box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5))
    return centers



def _create_stabilizer_transform(source_node, frame_boxes, reference_frame, shape_name):
    """
    Create a Transform node that stabilizes the input using the bbox center.

    The Transform.translate animation is the inverse movement of the bbox
    center, so the selected shape center stays locked to the reference frame
    center.
    """
    centers = _frame_centers(frame_boxes)

    ref_cx, ref_cy = centers[0][1], centers[0][2]
    for frame, cx, cy in centers:
        if frame == reference_frame:
            ref_cx, ref_cy = cx, cy
            break

    transform = nuke.createNode("Transform", inpanel=False)
    transform.setName("{}_BBox_Stabilize".format(source_node.name()))
    transform.setInput(0, source_node)
    transform['xpos'].setValue(source_node['xpos'].value() + 150)
    transform['ypos'].setValue(source_node['ypos'].value() + 80)
    transform['label'].setValue(
        "BBox center stabilization via Transform.translate\nShape: {}\nReference frame: {}".format(
            shape_name, int(reference_frame)
        )
    )

    if 'center' in transform.knobs():
        transform['center'].setValue(float(ref_cx), 0)
        transform['center'].setValue(float(ref_cy), 1)

    translate = transform['translate']
    translate.setAnimated()
    for frame, cx, cy in centers:
        translate.setValueAt(float(ref_cx - cx), int(frame), 0)
        translate.setValueAt(float(ref_cy - cy), int(frame), 1)

    _set_transform_filter_impulse(transform)
    return transform


def _ask_bbox_options(shapes):
    """Show one single dialog containing shape, crop mode, and offset options."""
    try:
        panel = nuke.PythonPanel("Roto BBox Crop Options")
        shape_names = [name for name, _shape in shapes]

        shape_knob = nuke.Enumeration_Knob("bbox_shape", "Shape", shape_names)
        mode_knob = nuke.Enumeration_Knob("bbox_mode", "Crop mode", CROP_MODES)
        offset_knob = nuke.String_Knob("bbox_offset", "Offset pixels")
        offset_knob.setValue("0")

        panel.addKnob(shape_knob)
        panel.addKnob(mode_knob)
        panel.addKnob(offset_knob)

        if not panel.showModalDialog():
            return None

        selected_shape_name = shape_knob.value()
        selected_mode = mode_knob.value()
        offset = _parse_offset(offset_knob.value())
    except Exception:
        # Fallback for older/minimal Nuke Python builds.
        shape_names = [name for name, _shape in shapes]
        panel = nuke.Panel("Roto BBox Crop Options")
        panel.addEnumerationPulldown("Shape", " ".join(["{%s}" % n for n in shape_names]))
        panel.addEnumerationPulldown("Crop mode", " ".join(["{%s}" % m for m in CROP_MODES]))
        panel.addSingleLineInput("Offset pixels", "0")
        panel.addButton("Cancel")
        panel.addButton("Create")
        if not panel.show():
            return None
        selected_shape_name = panel.value("Shape")
        selected_mode = panel.value("Crop mode")
        offset = _parse_offset(panel.value("Offset pixels"))

    if offset is None:
        return None

    shape_lookup = dict((name, shape) for name, shape in shapes)
    shape = shape_lookup.get(selected_shape_name)
    if shape is None:
        nuke.message("Could not find selected shape: {}".format(selected_shape_name))
        return None

    if selected_mode not in CROP_MODES:
        selected_mode = CROP_MODE_REGULAR

    return selected_shape_name, shape, selected_mode, offset


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def create_roto_bbox_node():
    selected = nuke.selectedNodes()
    if len(selected) != 1:
        nuke.message("Please select exactly one Roto or RotoPaint node.")
        return

    roto_node = selected[0]
    if roto_node.Class() not in ("Roto", "RotoPaint"):
        nuke.message("'{}' is not a Roto or RotoPaint node.".format(roto_node.name()))
        return

    shapes = _get_shape_names(roto_node)
    if not shapes:
        nuke.message("No shapes found inside '{}'.".format(roto_node.name()))
        return

    options = _ask_bbox_options(shapes)
    if options is None:
        return
    shape_name, shape, crop_mode, offset_value = options

    first = int(nuke.root()['first_frame'].value())
    last  = int(nuke.root()['last_frame'].value())
    total = last - first + 1
    frame_width, frame_height = _get_project_format_size()

    frame_boxes = []
    task = nuke.ProgressTask("Sampling roto bbox…")
    try:
        for i, frame in enumerate(range(first, last + 1)):
            if task.isCancelled():
                nuke.message("Cancelled.")
                return
            task.setProgress(int(100.0 * i / total))
            task.setMessage("Frame {}".format(frame))

            x, y, r, t = _shape_bbox_at_frame(shape, roto_node, frame)
            box = _int_box(
                x, y, r, t,
                offset=offset_value,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            frame_boxes.append((frame, box))
    finally:
        del task

    output_input = roto_node
    transform_node = None

    if crop_mode == CROP_MODE_STABILIZED:
        transform_node = _create_stabilizer_transform(roto_node, frame_boxes, first, shape_name)
        output_input = transform_node

    crop_node = nuke.createNode("Crop", inpanel=False)
    suffix = {
        CROP_MODE_REGULAR: "BBox",
        CROP_MODE_STATIC: "BBox_Static",
        CROP_MODE_STABILIZED: "BBox_Stabilized_Crop",
    }[crop_mode]
    crop_node.setName("{}_{}".format(roto_node.name(), suffix))
    crop_node['label'].setValue(
        "{}\nBBox: {}\nShape: {}\nOffset: {} px".format(
            crop_mode, roto_node.name(), shape_name, offset_value
        )
    )
    crop_node['crop'].setValue(False)
    _enable_crop_reformat(crop_node)
    crop_node.setInput(0, output_input)
    crop_node['xpos'].setValue(output_input['xpos'].value() + 150)
    crop_node['ypos'].setValue(output_input['ypos'].value())

    extra_transform_node = None
    post_crop_transform = None
    black_constant = None
    merge_node = None

    if crop_mode == CROP_MODE_REGULAR:
        _set_animated_box(crop_node, frame_boxes)
    elif crop_mode == CROP_MODE_STATIC:
        static_box = _union_box(frame_boxes)
        _set_static_box(crop_node, static_box)
        extra_transform_node = _create_static_crop_transform(crop_node, static_box, roto_node)
    elif crop_mode == CROP_MODE_STABILIZED:
        stabilized_static_box = _max_size_box_around_reference_center(
            frame_boxes,
            reference_frame=first,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        _set_static_box(crop_node, stabilized_static_box)
        if transform_node is not None:
            post_crop_transform, black_constant, merge_node = _create_stabilized_post_crop_chain(
                crop_node, stabilized_static_box
            )
            extra_transform_node = _create_matchmove_transform(transform_node, merge_node)

    created_nodes = []
    if transform_node is not None:
        created_nodes.append(transform_node.name())
    created_nodes.append(crop_node.name())
    if post_crop_transform is not None:
        created_nodes.append(post_crop_transform.name())
    if black_constant is not None:
        created_nodes.append(black_constant.name())
    if merge_node is not None:
        created_nodes.append(merge_node.name())
    if extra_transform_node is not None:
        created_nodes.append(extra_transform_node.name())
    created = " + ".join(created_nodes)

    return crop_node


if __name__ == "__main__":
    create_roto_bbox_node()
