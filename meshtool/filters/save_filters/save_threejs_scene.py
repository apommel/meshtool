import os
from meshtool.filters.base_filters import SaveFilter, FilterException
from itertools import chain
import numpy
import collada
import struct

INDENT = 3
SPACE = " "
NEWLINE = "\n"

def to_json(o, level=0):
    ret = ""
    if isinstance(o, dict):
        ret += "{" + NEWLINE
        comma = ""
        for k,v in o.iteritems():
            ret += comma
            comma = ",\n"
            ret += SPACE * INDENT * (level+1)
            ret += '"' + str(k) + '":' + SPACE
            ret += to_json(v, level + 1)
            
        ret += NEWLINE + SPACE * INDENT * level + "}"
    elif isinstance(o, basestring):
        ret += '"' + o + '"'
    elif isinstance(o, list):
        ret += "[" + ",".join([to_json(e, level+1) for e in o]) + "]"
    elif isinstance(o, int):
        ret += str(o)
    elif isinstance(o, float):
        ret += '%.7g' % o
    elif isinstance(o, numpy.ndarray) and numpy.issubdtype(o.dtype, numpy.integer):
        ret += "[" + ','.join(map(str, o.flatten().tolist())) + "]"
    elif isinstance(o, numpy.ndarray) and numpy.issubdtype(o.dtype, numpy.inexact):
        ret += "[" + ','.join(map(lambda x: '%.7g' % x, o.flatten().tolist())) + "]"
    else:
        raise TypeError("Unknown type '%s' for json serialization" % str(type(o)))
    return ret

def deccolor(c):
    return ( int(c[0] * 255) << 16  ) + ( int(c[1] * 255) << 8 ) + int(c[2] * 255)

def getMaterials(mesh):
    materials = {}
    for material in mesh.materials:
        effect = material.effect
        
        attrs = {}
        if effect.shadingtype == 'lambert':
            attrs['type'] = 'MeshLambertMaterial'
        elif effect.shadingtype == 'phong' or effect.shadingtype == 'blinn':
            attrs['type'] = 'MeshPhongMaterial'
        else:
            attrs['type'] = 'MeshBasicMaterial'
            
        params = {}
        attrs['parameters'] = params
        
        color_mapping = [('diffuse', 'color'),
                         ('ambient', 'ambient'),
                         ('specular', 'specular')]
        for effect_attr, three_name in color_mapping:
            val = getattr(effect, effect_attr, None)
            if val is not None:
                params[three_name] = deccolor(val)
        
        float_mapping = [('shininess', 'shininess'),
                         ('transparency', 'opacity')]
        for effect_attr, three_name in float_mapping:
            val = getattr(effect, effect_attr, None)
            if val is not None:
                params[three_name] = val
        
        materials[material.id] = attrs
        
    return materials

class FACE_BITS:
    # https://github.com/mrdoob/three.js/wiki/JSON-Model-format-3.0
    
    NUM_BITS = 8
    
    TRIANGLE_QUAD = 0
    # define these since they aren't simple on/off
    TRIANGLE = 0
    QUAD = 1
    
    # rest of these are on/off
    ON = 1
    OFF = 0
    
    FACE_MATERIAL = 1
    FACE_UVS = 2
    FACE_VERTEX_UVS = 3
    FACE_NORMAL = 4
    FACE_VERTEX_NORMALS = 5
    FACE_COLOR = 6
    FACE_VERTEX_COLORS = 7

def getEmbeds(mesh):
    embeds = {}
    
    for geom in mesh.geometries:
        for prim_num, prim in enumerate(geom.primitives):
            if isinstance(prim, collada.polylist.Polylist):
                prim = prim.triangleset()
            
            attrs = {}
            attrs["metadata"] = {"formatVersion": 3}
            attrs["scale"] = 1.0
            attrs["materials"] = []
            attrs["morphTargets"] = []
            attrs["colors"] = []
            attrs["edges"] = []
            
            attrs["vertices"] = prim.vertex if prim.vertex is not None else []
            attrs["normals"] = prim.normal if prim.normal is not None else []
            attrs["uvs"] = [texset for texset in prim.texcoordset]
            
            to_stack = [prim.vertex_index]
            type_bits = [0] * FACE_BITS.NUM_BITS
            type_bits[FACE_BITS.TRIANGLE_QUAD] = FACE_BITS.TRIANGLE
            if len(prim.texcoordset) > 0:
                type_bits[FACE_BITS.FACE_VERTEX_UVS] = FACE_BITS.ON
                to_stack.append(prim.texcoord_indexset[0])
            if prim.normal is not None:
                type_bits[FACE_BITS.FACE_VERTEX_NORMALS] = FACE_BITS.ON
                to_stack.append(prim.normal_index)

            type_code = int(''.join(map(str, reversed(type_bits))), 2)
            type_codes = numpy.empty((len(prim), 1), dtype=numpy.int32)
            type_codes[:] = type_code
            to_stack.insert(0, type_codes)
            
            stacked = numpy.hstack(to_stack)
            attrs["faces"] = stacked
            
            embeds["%s-primitive-%d" % (geom.id, prim_num)] = attrs
    
    return embeds

def FilterGenerator():
    class ThreeJsSceneSaveFilter(SaveFilter):
        def __init__(self):
            super(ThreeJsSceneSaveFilter, self).__init__('save_threejs_scene', 'Saves a collada model in three.js scene format')

        def apply(self, mesh, filename):
            if os.path.exists(filename):
                raise FilterException("specified filename already exists")
            
            outputfile = open(filename, "w")
            
            outdict = {}
            outdict['metadata'] = {'formatVersion': 3,
                                   'type': 'scene'}
            outdict['defaults'] = {'bgcolor': numpy.array([0,0,0], dtype=int)}
            outdict['objects'] = {}
            outdict['embeds'] = getEmbeds(mesh)
            outdict['geometries'] = {}
            for embed_name in outdict['embeds'].keys():
                outdict['geometries'][embed_name] = {'type': 'embedded_mesh', 'id': embed_name}
            outdict['materials'] = getMaterials(mesh)
            outdict['textures'] = {}
            
            outputfile.write(to_json(outdict))

            outputfile.close()
            return mesh

    return ThreeJsSceneSaveFilter()

from meshtool.filters import factory
factory.register(FilterGenerator().name, FilterGenerator)