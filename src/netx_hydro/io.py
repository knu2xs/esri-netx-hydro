import json
from pathlib import Path

import arcpy
import networkx as nx
from osgeo import ogr

__all__ = ['read_fgdb_fc']

def read_fgdb_fc(path, simplify=True, geom_attrs=True, strict=True):
    """Generates a networkx.DiGraph from an Esri File Geodatabase Feature 
    Class. Point geometries are translated into nodes, and lines into edges. 
    Coordinate tuples are used as keys. Attributes are preserved, line 
    geometries are simplified into start and end coordinates. Accepts a
    string path or pathlib.Path to a single Esri File Geodatabase Feature 
    Class.

    Parameters
    ----------
    path : string or pathlib.Path
        String path or pathlib.Path to a single Esri File Geodatabase 
        Feature Class to read.
    simplify:  bool
        If True, simplify line geometries to start and end coordinates.
        If False, and line feature geometry has multiple segments, the
        non-geometric attributes for that feature will be repeated for each
        edge comprising that feature.
    geom_attrs: bool
        If True, include the Wkb, Wkt and Json geometry attributes with
        each edge.
    strict: bool
        If True, raise NetworkXError when feature geometry is missing or
        GeometryType is not supported.
        If False, silently ignore missing or unsupported geometry in features.

    Returns
    -------
    G : NetworkX graph

    Raises
    ------
    ImportError
       If ogr module is not available.
    RuntimeError
       If file cannot be open or read.
    NetworkXError
       If strict=True and feature is missing geometry or GeometryType is
       not supported.

    Examples
    --------
    >>> G = nx.read_fgdb_fc('test.shp') # doctest: +SKIP
    """
    # ensure the path is a string
    path = str(path) if isinstance(path, Path) else path

    # create the graph to populate
    net = nx.DiGraph()

    # get a list of field names to work with
    field_name_lst = [fld.name for fld in arcpy.ListFields(nhdflowline_fc_pth) 
                      if fld.name != desc.shapeFieldName 
                      and fld.name != desc.OIDFieldName]

    # add geometry onto the end of the list for the cursor
    cur_fld_lst = field_name_lst + ['SHAPE@']

    # iterate the rows in the feature class
    with arcpy.da.SearchCursor(nhdflowline_fc_pth, cur_fld_lst) as cur:
        for row in cur:

            # get the geometry
            geom = row[-1]

            #  if the geometry is empty and following strict, blow up
            if geom is None:
                if strict:
                    raise nx.NetworkXError('Bad data: feature missing geometry')
                else:
                    continue

            # get data other than the geometry and marry it to the names
            field_data = row[:-1]
            attributes = dict(zip(field_name_lst, field_data))

            # if a point, simply add the point directly
            if geom.type == 'point':
                net.addNode((geom.centroid.X, geom.centroid.Y), **attributes)
            
            # if a polyline, there is more work to do
            elif geom.type == 'polyline':

                # get the paths from the geometry json
                paths = json.loads(geom.JSON)['paths']

                # load into net using helper function
                for edge in edges_from_esri_paths(paths, attributes, simplify, geom_attrs):
                    e1, e2, attr = edge
                    net.add_edge(e1, e2)
                    net[e1][e2].update(attr)

            # if neither one of these, this ain't gonna work
            else:
                raise Exception(f'Geometry type {geom_type} is not a supported geometry for a NetX Graph.')

            

    return


def edges_from_esri_paths(paths, attrs, simplify=True, geom_attrs=True):
    """
    Generate edges for each line in geom
    Written as a helper for read_fgdb_fc
    Parameters
    ----------
    paths:  paths object from Esri line geometry
        To be converted into an edge or edges
    attrs:  dict
        Attributes to be associated with all geoms
    simplify:  bool
        If True, simplify the line as in read_fgdb_fc
    geom_attrs:  bool
        If True, add geom attributes to edge as in read_fgdb_fc
    Returns
    -------
     edges:  generator of edges
        each edge is a tuple of form
        (node1_coord, node2_coord, attribute_dict)
        suitable for expanding into a networkx Graph add_edge call
    """
    # if not multiline
    if len(paths) == 1:
        
        # extract the path
        path = path[0]
        
        # get the edge attributes 
        edge_attrs = attrs.copy()
        
        # if simplifying the line
        if simplify:
            
            # create an ogr geometry object to work with
            segment = ogr.Geometry(ogr.wkbLineString)
            
            # add the first and last verticies to the segment
            segment.AddPoint_2D(path[0][:2])
            segment.AddPoint_2D(path[-1][:2])
            
            # if geometry attributes are being added, tack them on
            if geom_attrs:
                edge_attrs["Wkb"] = segment.ExportToWkb()
                edge_attrs["Wkt"] = segment.ExportToWkt()
                edge_attrs["Json"] = segment.ExportToJson()
                
            yield (segment.GetPoint_2D(0), segment.GetPoint_2D(1), edge_attrs)
            
        # if not simplifying
        else:
            
            # start iterating the vertex pair segments
            for i in range(len(path) - 1):
                
                # create an ogr geometry object to work with
                segment = ogr.Geometry(ogr.wkbLineString)

                # add the current and next verticies to the segment
                segment.AddPoint_2D(path[i][:2])
                segment.AddPoint_2D(path[i+1][:2])

                # if geometry attributes are being added, tack them on
                if geom_attrs:
                    edge_attrs["Wkb"] = segment.ExportToWkb()
                    edge_attrs["Wkt"] = segment.ExportToWkt()
                    edge_attrs["Json"] = segment.ExportToJson()

                yield (segment.GetPoint_2D(0), segment.GetPoint_2D(1), edge_attrs)
        
    # if multiline
    elif len(paths) > 1:
        
        # for every path in paths (representing continuous line segment)
        for i in range(len(paths)):
            
            # rip out the single ring for this iteration
            path_i = paths[i]
            
            # make it even more confusing to generate to this generator - yeah
            yeild from edges_from_esri_paths(path_i, attrs, simplify, geom_attrs)
