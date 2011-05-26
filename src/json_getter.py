# -*- coding: utf-8 -*-
from twms import projections
from libkomapnik import pixel_size_at_zoom
import json
import psycopg2
from mapcss import MapCSS
import sys
reload(sys)
sys.setdefaultencoding("utf-8")          # a hack to support UTF-8 

try:
  import psyco
  psyco.full()
except ImportError:
  debug("Psyco import failed. Program may run slower. If you run it on i386 machine, please install Psyco to get best performance.")

def get_vectors(bbox, zoom, style, vec = "polygon"):
  bbox_p = projections.from4326(bbox, "EPSG:3857")
  geomcolumn = "way"
  database = "dbname=gis"
  pxtolerance = 1.5
  intscalefactor = 10000
  ignore_columns = set(["way_area", "osm_id", geomcolumn])
  table = {"polygon":"planet_osm_polygon", "line":"planet_osm_line","point":"planet_osm_point"}
  a = psycopg2.connect(database)
  b = a.cursor()
  b.execute("SELECT * FROM %s LIMIT 1;" % table[vec])
  names = [q[0] for q in b.description]
  for i in ignore_columns:
    if i in names:
      names.remove(i)
  names = ",".join(['"'+i+'"' for i in names])


  taghint = "*"
  types = {"line":"line","polygon":"area", "point":"node"}
  adp = ""
  if "get_sql_hints" in dir(style):
    sql_hint = style.get_sql_hints(types[vec], zoom)
    adp = []
    for tp in sql_hint:
      add = []
      for j in tp[0]:
        if j not in names:
          break
      else:
        add.append(tp[1])
      if add:
        add = " OR ".join(add)
        add = "("+add+")"
        adp.append(add)
    adp = " OR ".join(adp)
    if adp:
      adp = adp.replace("&lt;", "<")
      adp = adp.replace("&gt;", ">")


  if vec == "polygon":
    query = """select ST_AsGeoJSON(ST_TransScale(ST_ForceRHR(ST_Intersection(way,SetSRID('BOX3D(%s %s,%s %s)'::box3d,900913))),%s,%s,%s,%s),0) as %s,
                      ST_AsGeoJSON(ST_TransScale(ST_ForceRHR(ST_PointOnSurface(way)),%s,%s,%s,%s),0) as reprpoint, %s from
              (select (ST_Dump(ST_Multi(ST_SimplifyPreserveTopology(ST_Buffer(way,-%s),%s)))).geom as %s, %s from
                (select ST_Union(way) as %s, %s from
                  (select ST_Buffer(way, %s) as %s, %s from
                     %s
                     where (%s)
                       and way && SetSRID('BOX3D(%s %s,%s %s)'::box3d,900913)
                       and way_area > %s
                  ) p
                 group by %s
                ) p
                where ST_Area(way) > %s
                order by ST_Area(way)
              ) p
      """%(bbox_p[0],bbox_p[1],bbox_p[2],bbox_p[3],
          -bbox_p[0],-bbox_p[1],intscalefactor/(bbox_p[2]-bbox_p[0]),intscalefactor/(bbox_p[3]-bbox_p[1]),
          geomcolumn,
          -bbox_p[0],-bbox_p[1],intscalefactor/(bbox_p[2]-bbox_p[0]),intscalefactor/(bbox_p[3]-bbox_p[1]),
          names,
          pixel_size_at_zoom(zoom, pxtolerance),pixel_size_at_zoom(zoom, pxtolerance),
          geomcolumn, names,
          geomcolumn, names,
          pixel_size_at_zoom(zoom, pxtolerance),
          geomcolumn, names,
          table[vec],
          adp,
          bbox_p[0],bbox_p[1],bbox_p[2],bbox_p[3],
          (pixel_size_at_zoom(zoom, pxtolerance)**2)/pxtolerance,
          names,
          pixel_size_at_zoom(zoom, pxtolerance)**2
          )
  elif vec == "line":
    query = """select ST_AsGeoJSON(ST_TransScale(ST_Intersection(way,SetSRID('BOX3D(%s %s,%s %s)'::box3d,900913)),%s,%s,%s,%s),0) as %s, %s from
              (select (ST_Dump(ST_Multi(ST_SimplifyPreserveTopology(ST_LineMerge(way),%s)))).geom as %s, %s from
                (select ST_Union(way) as %s, %s from
                     %s
                     where (%s)
                       and way && SetSRID('BOX3D(%s %s,%s %s)'::box3d,900913)
                      
                 group by %s
                ) p
                
              ) p
      """%(bbox_p[0],bbox_p[1],bbox_p[2],bbox_p[3],
          -bbox_p[0],-bbox_p[1],intscalefactor/(bbox_p[2]-bbox_p[0]),intscalefactor/(bbox_p[3]-bbox_p[1]),
          geomcolumn, names,
          pixel_size_at_zoom(zoom, pxtolerance),
          geomcolumn, names,
          geomcolumn, names,
          table[vec],
          adp,
          bbox_p[0],bbox_p[1],bbox_p[2],bbox_p[3],
          
          names,
          
          )
  elif vec == "point":
    query = """select ST_AsGeoJSON(ST_TransScale(way,%s,%s,%s,%s),0) as %s, %s
                from planet_osm_point where
                (%s)
                and way && SetSRID('BOX3D(%s %s,%s %s)'::box3d,900913)
               limit 3000
             """%(
             -bbox_p[0],-bbox_p[1],intscalefactor/(bbox_p[2]-bbox_p[0]),intscalefactor/(bbox_p[3]-bbox_p[1]),
             geomcolumn, names,
             adp,
             bbox_p[0],bbox_p[1],bbox_p[2],bbox_p[3],

             )
  #print query
  a = psycopg2.connect(database)
  b = a.cursor()
  b.execute(query)
  names = [q[0] for q in b.description]

  ROWS_FETCHED = 0
  polygons = []

  for row in b.fetchall():
    ROWS_FETCHED += 1
    geom = dict(map(None,names,row))
    for t in geom.keys():
      if not geom[t]:
        del geom[t]
    geojson = json.loads(geom[geomcolumn])
    del geom[geomcolumn]
    if "reprpoint" in geom:
      geojson["reprpoint"] = json.loads(geom["reprpoint"])["coordinates"]
      del geom["reprpoint"]
    geojson["properties"] = geom
    polygons.append(geojson)
  return {"bbox": bbox, "granularity":intscalefactor, "features":polygons}

style = MapCSS(0,20)
style.parse(open("styles/osmosnimki-maps.mapcss","r").read())  
bbox = (27.287430251477,53.80586321025,27.809624160147,53.99519870090)
bbox = (27.421874999999986, 53.748710796882726, 28.125, 54.162433968051523)

zoom = 12
aaaa = get_vectors(bbox,zoom,style,"polygon")
aaaa["features"].extend(get_vectors(bbox,zoom,style,"line")["features"])
aaaa["features"].extend(get_vectors(bbox,zoom,style,"point")["features"])

print json.dumps(aaaa,True,False,separators=(',', ':'))
