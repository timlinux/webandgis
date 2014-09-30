# coding=utf-8
"""Views for layers"""
import tempfile
import glob
import os

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from layers.models import Layer
from django.conf import settings
from safe.api import read_layer
from safe.api import calculate_impact
from safe.impact_functions.inundation.flood_OSM_building_impact import \
    FloodBuildingImpactFunction
# noinspection PyUnresolvedReferences
import safe.impact_functions.inundation.flood_polygon_roads
from subprocess import call
from django.contrib.auth.decorators import login_required
# noinspection PyUnresolvedReferences
from safe_qgis.utilities.qgis_layer_wrapper import QgisWrapper
# noinspection PyUnresolvedReferences
from safe_qgis.safe_interface import calculate_safe_impact

# noinspection PyUnresolvedReferences
from PyQt4.QtCore import QCoreApplication, QSize
from PyQt4.QtGui import QImage, QPainter, QColor
# noinspection PyUnresolvedReferences
from qgis.core import (
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsMapLayer,
    QgsRectangle,
    QgsMapRenderer,
    QgsMapLayerRegistry,
    QgsRectangle
)

QGIS_APP = None


def qgis_layers():
    """
    Helper to get loaded layers list in QGIS.

    :return: A list of layers.
    :rtype: str
    """
    r = QgsMapLayerRegistry.instance()
    registry_layers = r.mapLayers()
    registry_list = []
    for layer in registry_layers:
        registry_list.append(layer)
    return registry_list


def index(request):
    """Home page for layers.

    :param request: The web request.
    """
    r = QgsProviderRegistry.instance()
    providers = r.providerList()

    layers = Layer.objects.all()
    sizes = []
    for layer in layers:
        layer_path = os.path.join(
            settings.MEDIA_ROOT, 'layers', layer.slug, 'raw')
        map_layer = QgsVectorLayer(layer_path, layer.name, 'ogr')
        layer_size = map_layer.featureCount()
        layer.layer_size = layer_size
        del layer

    context = {
        'layers': layers,
        'providers': providers,
        'sizes': sizes}
    return render(request, 'layers/index.html', context)


def render_layers(layer_paths):
    """

    :param layer_paths: A list of layer paths.
    :return: Filename of rendered map
    """
    layer_uri = tempfile.NamedTemporaryFile(
        suffix='.png', prefix='inasafe-web-', dir='/tmp/').name
    # create image
    dim = 1000
    image = QImage(QSize(dim, dim), QImage.Format_ARGB32_Premultiplied)
    # set image's background color
    color = QColor(255, 255, 255, 0)
    image.fill(color.rgb())
    # create painter
    p = QPainter()
    p.begin(image)
    p.setRenderHint(QPainter.Antialiasing)
    renderer = QgsMapRenderer()
    layers = []

    for layer_path in layer_paths:
        map_layer = QgsVectorLayer(layer_path, None, 'ogr')
        QgsMapLayerRegistry.instance().addMapLayer(map_layer)

        # set layer set
        layers = [map_layer.id()]  # add ID of every layer

    renderer.setLayerSet(layers)
    # set extent
    rect = QgsRectangle(renderer.fullExtent())
    rect.scale(1.1)
    renderer.setExtent(rect)
    # set output size
    renderer.setOutputSize(image.size(), image.logicalDpiX())
    # do the rendering
    renderer.render(p)
    p.end()
    # clean up
    QgsMapLayerRegistry.instance().removeAllMapLayers()
    # save image
    image.save(layer_uri, 'png')
    return layer_uri


def preview(request, layer_slug):
    """Home page for layers.

    :param request: The web request.
    :param layer_slug: The layer
    """
    layer = get_object_or_404(Layer, slug=layer_slug)

    layer_path = shapefile_path(layer.name)
    layer_uri = render_layers([layer_path])
    with open(layer_uri, 'rb') as f:
        response = HttpResponse(f.read(), content_type='png')
    # os.remove(layer_uri)

    return response


def detail(request, layer_slug):
    """Ariel must document his code!
    :param layer_slug:
    :param request:
    """
    layer = get_object_or_404(Layer, slug=layer_slug)

    #get GeoJSON file
    layer_folder = os.path.join(settings.MEDIA_URL, 'layers', layer_slug)
    geometry_json = os.path.join(layer_folder, 'raw', 'geometry.json')
    context = {'layer': layer, 'geojson': geometry_json}

    return render(request, 'layers/detail.html', context)


def shapefile_path(layer_name):
    layer = Layer.objects.get(name=layer_name)
    layer_path = os.path.join(settings.MEDIA_ROOT, 'layers', layer.slug, 'raw')
    os.chdir(layer_path)
    filename = glob.glob('*.shp')[0]
    layer_file = os.path.join(layer_path, filename)
    return layer_file


def get_layer_data(layer_name):
    """

    :param layer_name:
    :return:
    """
    layer_file = shapefile_path(layer_name)
    return read_layer(layer_file)


@login_required(redirect_field_name='next')
def calculate(request):
    """Calculates the buildings affected by flood.
    :param request:
    """

    output = os.path.join(settings.MEDIA_ROOT, 'layers', 'impact.json')

    buildings = get_layer_data('Buildings')
    flood = get_layer_data('Flood')

    # assign the required keywords for inasafe calculations
    buildings.keywords['category'] = 'exposure'
    buildings.keywords['subcategory'] = 'structure'
    flood.keywords['category'] = 'hazard'
    flood.keywords['subcategory'] = 'flood'

    impact_function = FloodBuildingImpactFunction
    # run analisys
    impact_file = calculate_impact(
        layers=[buildings, flood],
        impact_fcn=impact_function
    )

    flood_path = shapefile_path('Flood')
    impact_path = impact_file.filename
    render_layers([flood_path, impact_path])

    call(['ogr2ogr', '-f', 'GeoJSON',
          output, impact_file.filename])

    impact_geojson = os.path.join(settings.MEDIA_URL, 'layers', 'impact.json')

    context = impact_file.keywords
    context['geojson'] = impact_geojson
    context['user'] = request.user

    return render(request, 'layers/calculate.html', context)
