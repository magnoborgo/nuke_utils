import nuke
import math
import nukescripts

def tracker_to_bbox():
    node = nuke.selectedNode()
    if node.Class() != "Tracker3":
        print("not a tracker node")
        return

    #===========================================================================
    # panel setup
    #===========================================================================
    p = nukescripts.panels.PythonPanel("Tracker to Bbox")
    k = nuke.String_Knob("framerange","FrameRange")
    k.setFlag(nuke.STARTLINE)    
    k.setTooltip("Set the framerange")
    p.addKnob(k)
    k.setValue("%s-%s" % (nuke.root().firstFrame(), nuke.root().lastFrame())) 
    k = nuke.Boolean_Knob("curvet", "Create CurveTool")
    k.setFlag(nuke.STARTLINE)
    k.setTooltip("Create CurveTool instead of Crop")
    p.addKnob(k)
    result = p.showModalDialog()   

    if result == 0:
        return # Canceled
    try:
        fRange = nuke.FrameRange(p.knobs()["framerange"].getText())
    except:
        if nuke.GUI:
            nuke.message( 'Framerange format is not correct, use startframe-endframe i.e.: 0-200' )
        return

    curvetool  =p.knobs()["curvet"].value()

    if curvetool:
        ct = nukescripts.createCurveTool()
        ct = nuke.selectedNode()
        bboxknob = "ROI"

    else:
        ct = nuke.createNode("Crop")
        bboxknob = "box"

    ct[bboxknob].setAnimated()

    to1 = node["track1"]
    to2 = node["track2"]
    to3 = node["track3"]
    to4 = node["track4"]
        
    for f in fRange:
        trk1_x = node["track1"].animations()[0].evaluate(f)
        trk1_y = node["track1"].animations()[1].evaluate(f)
        trk2_x = node["track2"].animations()[0].evaluate(f)
        trk2_y = node["track2"].animations()[1].evaluate(f)
        trk3_x = node["track3"].animations()[0].evaluate(f)
        trk3_y = node["track4"].animations()[1].evaluate(f)
        trk4_x = node["track4"].animations()[0].evaluate(f)
        trk4_y = node["track4"].animations()[1].evaluate(f)
        bbox_x = math.floor(min(trk1_x,trk2_x,trk3_x,trk4_x))
        bbox_y = math.floor(min(trk1_y,trk2_y,trk3_y,trk4_y))
        bbox_w = math.ceil(max(trk1_x,trk2_x,trk3_x,trk4_x))
        bbox_h = math.ceil(max(trk1_y,trk2_y,trk3_y,trk4_y))

        k = ct[bboxknob].animations()
        k[0].setKey(f, bbox_x)
        k[1].setKey(f, bbox_y) 
        k[2].setKey(f, bbox_w)
        k[3].setKey(f, bbox_h)        


if __name__ == '__main__':
   tracker_to_bbox()