import nuke
import os
import nukescripts
import logging
log = logging.getLogger(__name__)
log.info("Loading %s " % os.path.abspath(__file__))

__version__ = "1.0.1"
__author__ = "Magno Borgo"
__creation__ = "October 09 2014"
__date__ = "Aug 20 2023"
__web__ = "www.boundaryvfx.com"

BVFX_DEFAULT_SHORTCUT = ""
BVFX_DEFAULT_MENULABEL = "Curve Tool to Grade"

'''simple example menu.py:
import bvfx_curvetool2grade
toolbar = nuke.menu("Nodes")
bvfxt = toolbar.addMenu("BoundaryVFX Tools")
bvfxt.addCommand('CurveTool2Grade', 'bvfx_curvetool2grade.main()')
'''

def main():
    ''' Copy CurveTool intensity Data to a Grade Node

     "offset" with the desired frame offset
    '''
    curvetNode = nuke.selectedNode()

    if curvetNode.Class() not in ('CurveTool'):
        raise TypeError(
            'Unsupported node type. Selected Node must be CurveTool')

    # UI setup
    p = nukescripts.panels.PythonPanel("CurveTool to Grade")
    p.size = [500,100]
    k = nuke.Int_Knob("ref_frame", "Reference Frame")
    k.setFlag(nuke.STARTLINE)
    k.setTooltip(
        "The reference frame, the rest of the animation will be relative/offset from this frame")
    k.setValue(nuke.root().firstFrame())
    p.addKnob(k)
    k = nuke.Enumeration_Knob('mode', 'mode', ['colormatch: whites', 'colormatch: blacks',
                                                'colormatch: blacks by hypot',
                                               'stabilize plate whites', 'stabilize plate blacks',
                                                'stabilize by offset', 'all'])
    k.setFlag(nuke.STARTLINE)
    k.setTooltip(
        "Plus mode is a grade using offset, mult will use whitepoint/gain")
    p.addKnob(k)
    result = p.showModalDialog()
    if not result:
        return  # Canceled

    mode = p.knobs()["mode"].value()
    ref_frame = p.knobs()["ref_frame"].value()
    # end of ui setup

    if mode in ["stabilize by offset", "all"]:
        newgrade = nuke.createNode("Grade", inpanel=False)
        tab = nuke.Tab_Knob('Reference Frame')
        newgrade.addKnob(tab)
        at = nuke.Int_Knob('frame_offset')
        at.setValue(ref_frame)
        newgrade.addKnob(at)
        newgrade["black_clamp"].setValue(False)
        newgrade["label"].setValue(
            "mode: stabilize by offset\nref frame [value frame_offset]")
        coloroffset = newgrade['add']
        coloroffset.setValue([0, 0, 0, 0])
        coloroffset.setAnimated()
        coloroffset.copyAnimation(0, curvetNode['intensitydata'].animation(0))
        coloroffset.copyAnimation(1, curvetNode['intensitydata'].animation(1))
        coloroffset.copyAnimation(2, curvetNode['intensitydata'].animation(2))
        coloroffset.setExpression("curve-curve(([value frame_offset]))", 0)
        coloroffset.setExpression("curve-curve(([value frame_offset]))", 1)
        coloroffset.setExpression("curve-curve(([value frame_offset]))", 2)

    if mode in ["stabilize plate whites", "all"]:
        newgrade = nuke.createNode("Grade", inpanel=False)
        tab = nuke.Tab_Knob('Reference Frame')
        newgrade.addKnob(tab)
        at = nuke.Int_Knob('frame_offset')
        at.setValue(ref_frame)
        newgrade.addKnob(at)
        newgrade["black_clamp"].setValue(False)
        newgrade["label"].setValue(
            "mode: stabilize plate whites\nref frame [value frame_offset]")
        coloroffset = newgrade['whitepoint']
        coloroffset.setValue([0, 0, 0, 0])
        coloroffset.setAnimated()
        coloroffset.copyAnimation(0, curvetNode['intensitydata'].animation(0))
        coloroffset.copyAnimation(1, curvetNode['intensitydata'].animation(1))
        coloroffset.copyAnimation(2, curvetNode['intensitydata'].animation(2))
        gain = newgrade['white']
        gain.setValue([0, 0, 0, 0])
        gain.setAnimated()
        gain.setExpression("whitepoint([value frame_offset])", 0)
        gain.setExpression("whitepoint([value frame_offset])", 1)
        gain.setExpression("whitepoint([value frame_offset])", 2)

    if mode in ["stabilize plate blacks", "all"]:
        newgrade = nuke.createNode("Grade", inpanel=False)
        tab = nuke.Tab_Knob('Reference Frame')
        newgrade.addKnob(tab)
        at = nuke.Int_Knob('frame_offset')
        at.setValue(ref_frame)
        newgrade.addKnob(at)
        newgrade["black_clamp"].setValue(False)
        newgrade["label"].setValue(
            "mode: stabilize plate blacks\nref frame [value frame_offset]")
        coloroffset = newgrade['blackpoint']
        coloroffset.setValue([0, 0, 0, 0])
        coloroffset.setAnimated()
        coloroffset.copyAnimation(0, curvetNode['intensitydata'].animation(0))
        coloroffset.copyAnimation(1, curvetNode['intensitydata'].animation(1))
        coloroffset.copyAnimation(2, curvetNode['intensitydata'].animation(2))
        gain = newgrade['black']
        gain.setValue([0, 0, 0, 0])
        gain.setAnimated()
        gain.setExpression("blackpoint([value frame_offset])", 0)
        gain.setExpression("blackpoint([value frame_offset])", 1)
        gain.setExpression("blackpoint([value frame_offset])", 2)
    if mode in ["colormatch: whites", "all"]:
        newgrade = nuke.createNode("Grade", inpanel=False)
        newgrade["black_clamp"].setValue(False)
        newgrade["label"].setValue(
            "mode: colormatch whites\nref frame [value frame_offset]")
        coloroffset = newgrade['white']
        coloroffset.setValue([0, 0, 0, 0])
        coloroffset.setAnimated()
        coloroffset.copyAnimation(0, curvetNode['intensitydata'].animation(0))
        coloroffset.copyAnimation(1, curvetNode['intensitydata'].animation(1))
        coloroffset.copyAnimation(2, curvetNode['intensitydata'].animation(2))
    if mode in ["colormatch: blacks", "all"]:
        newgrade = nuke.createNode("Grade", inpanel=False)
        newgrade["black_clamp"].setValue(False)
        newgrade["label"].setValue(
            "mode: colormatch blacks\nref frame [value frame_offset]")
        coloroffset = newgrade['black']
        coloroffset.setValue([0, 0, 0, 0])
        coloroffset.setAnimated()
        coloroffset.copyAnimation(0, curvetNode['intensitydata'].animation(0))
        coloroffset.copyAnimation(1, curvetNode['intensitydata'].animation(1))
        coloroffset.copyAnimation(2, curvetNode['intensitydata'].animation(2))
    if mode in ["colormatch: blacks by hypot", "all"]:
        newgrade = nuke.createNode("Constant", inpanel=False)
        newgrade["label"].setValue(
            "mode: colormatch blacks\nref frame [value frame_offset]")

        coloroffset = newgrade['color']
        coloroffset.setValue([0, 0, 0, 0])
        coloroffset.setAnimated()
        coloroffset.copyAnimation(0, curvetNode['intensitydata'].animation(0))
        coloroffset.copyAnimation(1, curvetNode['intensitydata'].animation(1))
        coloroffset.copyAnimation(2, curvetNode['intensitydata'].animation(2))
        merge = nuke.createNode("Merge2", inpanel=False)
        merge["operation"].setValue("hypot")
    

if __name__ == '__main__':
    main()
