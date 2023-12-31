# Script to render a sequence of ply files with Blender. First, setup your scene
# and material for the imported meshes. Scene must be in "OBJECT"-mode.
# Fill in variables in options.
# References.
# See: http://blender.stackexchange.com/questions/24133/modify-obj-after-import-using-python
# and: http://blenderartists.org/forum/showthread.php?320309-How-to-import-ply-files-from-script
import bpy
from typing import Tuple
import struct

# Options.
meshFolders = ["output/drop0", "output/drop1"]  # Folder without ending "\\".
renderFolder = "output/render"  # Output folder (without ending "\\").
AmountOfNumbers = 1  # Amount of numbers in filepath, e.g., 000010.ply

# -------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------
M_PI = 3.1415926535897932
END_FRAME = 300
ANIM_STEP = 8 # amt of time between frames
USE_ANIM = True
RENDER_FRAMES = False
RENDER_ENGINE = 'BLENDER_EEVEE'
CAMERA_LOCATION = [7,7,100]
NUM_INK_MESH = 2

# Grid Constants
DIMENSIONS = (8,25,8)
GRID_THICKNESS = 0.01 # thickness of grid lines
BORDER_THICKNESS = 0.1 # thickness of grid border
SHOW_GRID = True # show the grid lines; otherwise, the just the grid border is shown
#------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------

# Helpers

def SelectOnlyGivenObject(object):
	# Firs deselect all.
	for iterationObject in bpy.context.scene.objects:
		iterationObject.select_set(False)
	# Then select the given object.
	object.select_set(True)

# Delete an object, see: http://blender.stackexchange.com/questions/27234/python-how-to-completely-remove-an-object
def DeleteObject(object):
	# Cache the currrent mode we are in.
	#oldMode = bpy.context.mode
	# Set it to object mode.
	#bpy.ops.object.mode_set(mode = 'OBJECT')
	# Select only the given object.
	SelectOnlyGivenObject(object)
	# Delete the object and set the mode back to where it was.
	bpy.ops.object.delete()
	#bpy.ops.object.mode_set(mode = oldMode)

def MeshPath(folder = "", frame = 0, fileEnding = "ply"):
	return folder + "/" + str(frame).zfill(AmountOfNumbers) + "." + fileEnding

def RenderPath(folder = "", frame = 0, fileEnding = "png"):
	return folder + "/" + str(frame).zfill(4) + "." + fileEnding

def create_camera(location: Tuple[float, float, float]) -> bpy.types.Object:
    bpy.ops.object.camera_add(location=location)
    return bpy.context.object

def focus_camera_on_object(camera_object):
	# focus on object -> NOT USED BUT MAY USE LATER
	for area in bpy.context.screen.areas:
		if area.type == 'VIEW_3D':
			for region in area.regions:
				if region.type == 'WINDOW':
					override = {'area': area, 'region': region}
					bpy.ops.view3d.camera_to_view_selected(override)

	camera_object.location[2] += 2
	camera_object.values().lens = 50

def create_light(location):
	# Create light datablock
	light_data = bpy.data.lights.new(name="pointlight-data", type='POINT')
	light_data.energy = 10000
	light_data.distance = 20

	# Create new object, pass the light data 
	light_object = bpy.data.objects.new(name="my-light", object_data=light_data)

	# Link object to collection in context
	bpy.context.collection.objects.link(light_object)

	# Change light position
	light_object.location = location
	return light_object


def create_grid():
	# create the first cube
	bpy.ops.mesh.primitive_cube_add(enter_editmode=False, location=(0,0,0), scale=(0.5,0.5,0.5))
	cube = bpy.context.selected_objects[0]
	for i in range(3):
		mod = cube.modifiers.new('Array_' + str(i), 'ARRAY')
		mod.relative_offset_displace[0] = 0
		mod.relative_offset_displace[i] = 1
		mod.count = DIMENSIONS[i]
	cube.modifiers.new('WD', 'WELD')
	wf = cube.modifiers.new('WF', 'WIREFRAME') 
	wf.thickness = GRID_THICKNESS
	 # shift grid (aka. shift center of first cube after scaling)
	cube.location = [0.5, 0.5, 0.5]

def create_border():
	grid_location = [DIMENSIONS[0]/2, DIMENSIONS[1]/2, DIMENSIONS[2]/2]
	grid_scale = grid_location
	bpy.ops.mesh.primitive_cube_add(enter_editmode=False, location=grid_location, scale=grid_scale)
	cube = bpy.context.selected_objects[0]
	wf = cube.modifiers.new('WF', 'WIREFRAME') 
	wf.thickness = BORDER_THICKNESS

def setBackgroundColor():
	# Set the background color to white
	bpy.context.scene.render.film_transparent = False
	bpy.context.scene.render.image_settings.color_mode = 'RGB'
	bpy.context.scene.render.image_settings.color_depth = '8'
	bpy.context.scene.view_settings.view_transform = 'Standard'
	bpy.context.scene.view_settings.look = 'None'
	bpy.context.scene.view_settings.exposure = 0.0
	bpy.context.scene.world.use_nodes = True
	bpy.context.scene.world.node_tree.nodes["Background"].inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)

def makeInkMaterial(color):
	material = bpy.data.materials.new(name="Ink Material")
	material.use_nodes = True
	material_output = material.node_tree.nodes.get('Material Output')
	principled_bsdf = material.node_tree.nodes.get('Principled BSDF')
	principled_bsdf.inputs["Emission"].default_value = color
	hue_saturation = material.node_tree.nodes.new('ShaderNodeHueSaturation')
	hue_saturation.location.x -= 200
	hue_saturation.location.y -= 50
	attribute = material.node_tree.nodes.new('ShaderNodeAttribute')
	attribute.location.x -= 500
	attribute.location.y -= 50
	# connect shader nodes
	material.node_tree.links.new(attribute.outputs["Color"], hue_saturation.inputs["Color"])
	material.node_tree.links.new(hue_saturation.outputs["Color"], principled_bsdf.inputs["Base Color"])
	material.node_tree.links.new(principled_bsdf.outputs["BSDF"], material_output.inputs["Surface"])
	return material


def createGeometryNodes(importedObject, object_material):
	## Make and link geometry nodes
	# https://blender.stackexchange.com/questions/259867/geometry-nodes-as-mesh-generation-script
	# 2) Add the GeometryNodes Modifier
	modifier = importedObject.modifiers.new("GeometryNodesNew", "NODES")
	print(modifier.name, modifier)
	# https://blender.stackexchange.com/questions/249763/python-geometry-node-trees/249779#249779
	def new_GeometryNodes_group():
		''' Create a new empty node group that can be used
			in a GeometryNodes modifier.
		'''
		node_group = bpy.data.node_groups.new('GeometryNodes', 'GeometryNodeTree')
		inNode = node_group.nodes.new('NodeGroupInput')
		inNode.outputs.new('NodeSocketGeometry', 'Geometry')
		outNode = node_group.nodes.new('NodeGroupOutput')
		outNode.inputs.new('NodeSocketGeometry', 'Geometry')
		node_group.links.new(inNode.outputs['Geometry'], outNode.inputs['Geometry'])
		return node_group
	# In 3.2 Adding the modifier no longer automatically creates a node group.
	# This test could be done with versioning, but this approach is more general
	# in case a later version of Blender goes back to including a node group.
	node_group = None
	if importedObject.modifiers[-1].node_group:
		node_group = importedObject.modifiers[-1].node_group    
	else:
		node_group = new_GeometryNodes_group()
		importedObject.modifiers[-1].node_group = node_group
	nodes = node_group.nodes
	# ---- ---- ---- ---- KEEP FOR NOW---- ---- ---- ---- ---- 
	# meshpoint = nodes.new(type="GeometryNodeMeshToPoints")
	# meshpoint.location.x += 400
	# meshpoint.location.y -= 50
	# # connect
	# links = node_group.links
	# links.new(nodes["Group Input"].outputs["Geometry"], meshpoint.inputs["Mesh"])
	# links.new(meshpoint.outputs["Points"], nodes["Group Output"].inputs["Geometry"])
	#---- ---- ---- ---- ---- ---- ---- ---- ---- ---- -------- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---
	instance_on_points = nodes.new(type="GeometryNodeInstanceOnPoints")
	instance_on_points.location.x += 300
	instance_on_points.location.y -= 50
	realize_instances = nodes.new(type="GeometryNodeRealizeInstances")
	realize_instances.location.x += 500
	realize_instances.location.y -= 50
	primitive = nodes.new(type="GeometryNodeMeshIcoSphere")
	primitive.location.x -= 100
	primitive.location.y -= 200
	primitive.inputs["Radius"].default_value = 0.06
	set_material= nodes.new(type="GeometryNodeSetMaterial")
	set_material.location.x += 100
	set_material.location.y -= 200
	set_material.inputs["Material"].default_value = object_material
	# connect
	links = node_group.links
	links.new(nodes["Group Input"].outputs["Geometry"], instance_on_points.inputs["Points"])
	links.new(instance_on_points.outputs["Instances"], realize_instances.inputs["Geometry"])
	links.new(realize_instances.outputs["Geometry"], nodes["Group Output"].inputs["Geometry"])
	links.new(primitive.outputs["Mesh"], set_material.inputs["Geometry"])
	links.new(set_material.outputs["Geometry"], instance_on_points.inputs["Instance"])


# ---------- ---------- ---------- ---------- ---------- ----------
# CODE FROM: https://github.com/CGArtPython/bpy_building_blocks_examples/tree/main/clean_scene
def purge_orphans():
    if bpy.app.version >= (3, 0, 0):
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True, do_linked_ids=True, do_recursive=True
        )
    else:
        # call purge_orphans() recursively until there are no more orphan data blocks to purge
        result = bpy.ops.outliner.orphans_purge()
        if result.pop() != "CANCELLED":
            purge_orphans()

def clean_scene():
    """
    Removing all of the objects, collection, materials, particles,
    textures, images, curves, meshes, actions, nodes, and worlds from the scene
    """
    bpy.context.scene.render.engine = RENDER_ENGINE
    if bpy.context.active_object and bpy.context.active_object.mode == "EDIT":
        bpy.ops.object.editmode_toggle()

    for obj in bpy.data.objects:
        obj.hide_set(False)
        obj.hide_select = False
        obj.hide_viewport = False

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    collection_names = [col.name for col in bpy.data.collections]
    for name in collection_names:
        bpy.data.collections.remove(bpy.data.collections[name])

    # in the case when you modify the world shader
    world_names = [world.name for world in bpy.data.worlds]
    for name in world_names:
        bpy.data.worlds.remove(bpy.data.worlds[name])
    # create a new world data block
    bpy.ops.world.new()
    bpy.context.scene.world = bpy.data.worlds["World"]
    purge_orphans()
    
# ---------- ---------- ---------- ---------- ---------- ----------

def create_animation(anim_data, mesh, frames):
	def insert_keyframe(fcurves, frame, values):
		for fcu, val in zip(fcurves, values):
			fcu.keyframe_points.insert(frame, val, options={'FAST'})

	me = mesh.data
	action = bpy.data.actions.new("MeshAnimation")
	me.animation_data_create()
	me.animation_data.action = action
	data_path = "vertices[%d].co"
	for index, v in enumerate(me.vertices):
		fcurves = [action.fcurves.new(data_path % v.index, index =  i) for i in range(3)]
		print(index)
		for t in frames:
			co_kf = anim_data[t-1][index]
			insert_keyframe(fcurves, t, co_kf)

def render_animation():
	# Set the output directory and file format
	output_dir = renderFolder
	file_format = "AVI_JPEG"  # Or use "FFMPEG" for better video quality

	# Set the output format and file name
	bpy.context.scene.render.image_settings.file_format = file_format
	bpy.context.scene.render.filepath = output_dir + "/animation"

	# Render the animation
	print("Rendering the animation. ")
	bpy.ops.render.render(animation=True)
#------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------
def getVertsFromBinary(path_to_ply):
	# Open the PLY file in binary mode
	with open(path_to_ply, "rb") as f:
		# Read the header to get the number of vertices and faces
		header = ""
		while "end_header" not in header:
			line = f.readline().decode("utf-8")
			header += line
			if "element vertex" in line:
				num_verts = int(line.split()[-1])				
		# Read the binary data for the vertices
		verts = []
		for i in range(num_verts):
			vert_data = struct.unpack("<fff", f.read(12))
			verts.append(vert_data)
	print(path_to_ply)
	return verts

def make_and_link_mesh(verts):
	mesh_data = bpy.data.meshes.new(name="NewMesh")
	mesh_data.from_pydata(verts, [], [])
	mesh_data.update()

	# Create a new object and link it to the scene
	obj = bpy.data.objects.new(name="NewObject", object_data=mesh_data)
	bpy.context.scene.collection.objects.link(obj)
	return obj

#------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------

def get_data(startFrame, endFrame, material, ply_folder):
	# Loop over the frames.
	ink_mesh = None
	# light_created = False
	data = []
	for currentFrame in range(startFrame, endFrame):
		## Get mesh info from ply
		fullPathToMesh = MeshPath(folder = ply_folder, frame = currentFrame)
		verts = getVertsFromBinary(fullPathToMesh)

		## Make the just imported object.
		importedObject = make_and_link_mesh(verts)
			
		if ink_mesh is not None:
			data.append(verts)
			if RENDER_FRAMES:
				for i in range(len(ink_mesh.data.vertices)):
					ink_mesh.data.vertices[i].co = verts[i]
			DeleteObject(importedObject)
		else:
			## Make and link geometry nodes -- here is where material is linked as well
			createGeometryNodes(importedObject, material)			
			ink_mesh = importedObject
			data.append(verts)

		# Render the scene.
		if RENDER_FRAMES:
			bpy.data.scenes['Scene'].render.filepath = RenderPath(folder = renderFolder, frame = currentFrame)
			# bpy.data.scenes["Scene"].camera = camera_object #UNSURE IF THIS IS OKAY TO COMMENT OUG
			bpy.ops.render.render(write_still = True) 
	return ink_mesh, data


def RenderSequence(startFrame = 0, endFrame = 1):
	# Clear the scene:
	clean_scene()

	# Set background color
	setBackgroundColor()

	# create camera
	camera_object = create_camera(location=(0.0, 0.0, 0.0))
	bpy.context.scene.camera = camera_object
	camera_object.location = CAMERA_LOCATION

	# create grid
	if SHOW_GRID:
		create_grid()
	create_border()

	## Lighting
	create_light(camera_object.location)

	# set render settings
	bpy.context.scene.frame_end = endFrame
	bpy.context.scene.frame_step = 1
	bpy.context.scene.eevee.use_motion_blur = True
	bpy.context.scene.eevee.motion_blur_shutter = 5.0
	bpy.context.scene.eevee.motion_blur_max = 100
	bpy.context.scene.eevee.motion_blur_steps = 10

	frames = list(range(startFrame, endFrame))

	for i in range(NUM_INK_MESH):
		# make the material
		color  = (.001 + i/NUM_INK_MESH, .01, .01, float(.5))
		material = makeInkMaterial(color)
		folder_filepath = meshFolders[i]
		ink_mesh, data = get_data(startFrame, endFrame, material, folder_filepath)
		if USE_ANIM:
			print("USING ANIM")
			create_animation(data, ink_mesh, frames)
	if USE_ANIM:
		render_animation()
		

	# # Loop over the frames.
	# ink_mesh = None
	# # light_created = False
	# data = []
	# for currentFrame in range(startFrame, endFrame):
	# 	## Get mesh info from ply
	# 	fullPathToMesh = MeshPath(folder = meshFolder, frame = currentFrame)
	# 	verts = getVertsFromBinary(fullPathToMesh)

	# 	## Make the just imported object.
	# 	importedObject = make_and_link_mesh(verts)
			
	# 	## Camera
	# 	camera_object.location = CAMERA_LOCATION

	# 	if ink_mesh is not None:
	# 		data.append(verts)
	# 		if RENDER_FRAMES:
	# 			for i in range(len(ink_mesh.data.vertices)):
	# 				ink_mesh.data.vertices[i].co = verts[i]
	# 		DeleteObject(importedObject)
	# 	else:
	# 		## Make and link geometry nodes -- here is where material is linked as well
	# 		createGeometryNodes(importedObject, material)
	# 		# ## lighting
	# 		# if not light_created:
	# 		# 	create_light(camera_object.location)
	# 		# 	light_created = True
			
	# 		ink_mesh = importedObject
	# 		data.append(verts)

	# 	# Render the scene.
	# 	if RENDER_FRAMES:
	# 		bpy.data.scenes['Scene'].render.filepath = RenderPath(folder = renderFolder, frame = currentFrame)
	# 		bpy.data.scenes["Scene"].camera = camera_object
	# 		bpy.ops.render.render(write_still = True) 
	# # return ink_mesh, data

	# if USE_ANIM:
	# 	print("USING ANIM")
	# 	bpy.context.scene.eevee.use_motion_blur = True
	# 	bpy.context.scene.eevee.motion_blur_shutter = 5.0
	# 	bpy.context.scene.eevee.motion_blur_max = 100
	# 	bpy.context.scene.eevee.motion_blur_steps = 10
	# 	frames = list(range(startFrame, endFrame))
	# 	create_animation(data, ink_mesh, frames)
	# 	render_animation()


		

# Run the script.
RenderSequence(startFrame = 1, endFrame = END_FRAME)
