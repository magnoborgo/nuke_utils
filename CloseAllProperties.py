import nuke
def CloseAllProperties():
	for n in nuke.allNodes(recurseGroups=True):
		n.hideControlPanel()
	nuke.root().hideControlPanel()

if __name__ == "__main__":
	CloseAllProperties()

### add to your menu.py
# import CloseAllProperties
# nuke.menu('Nuke').addCommand('Extra/Close All Properties',"CloseAllProperties.CloseAllProperties()", "]")
