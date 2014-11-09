# coding=utf-8
"""Views for layers"""
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
from PyQt4.QtCore import QCoreApplication, QSize, QBuffer, QIODevice

# noinspection PyUnresolvedReferences
from qgis.core import (
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsMapLayer,
    QgsRectangle,
    QgsMapRenderer,
    QgsMapLayerRegistry,
    QgsRectangle,
    QgsMapSettings,
    QgsMapRendererSequentialJob,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
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
    :return: Buffer containing output. Note caller is responsible for closing
        the buffer with buffer.close()
    :rtype: QBuffer
    """
    layers = []
    extent = None


    crs = QgsCoordinateReferenceSystem()
    crs.createFromSrid(3857)

    for layer_path in layer_paths:
        map_layer = QgsVectorLayer(layer_path, None, 'ogr')
        QgsMapLayerRegistry.instance().addMapLayer(map_layer)
        transform = QgsCoordinateTransform(map_layer.crs(), crs)
        print map_layer.extent().toString()
        layer_extent = transform.transform(map_layer.extent())
        if extent is None:
            extent = layer_extent
        else:
            extent.combineExtentWith(layer_extent)
        print extent.toString()
        # set layer set
        layers.append(map_layer.id())  # add ID of every layer

    map_settings = QgsMapSettings()

    map_settings.setDestinationCrs(crs)
    map_settings.setCrsTransformEnabled(True)
    map_settings.setExtent(extent)
    map_settings.setOutputSize(QSize(1000, 1000))

    map_settings.setLayers(layers)

    # job = QgsMapRendererParallelJob(settings)
    job = QgsMapRendererSequentialJob(map_settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    # Save teh image to a buffer
    map_buffer = QBuffer()
    map_buffer.open(QIODevice.ReadWrite)
    image.save(map_buffer, "PNG")
    image.save('/tmp/test.png', 'png')

    # clean up
    QgsMapLayerRegistry.instance().removeAllMapLayers()

    return map_buffer


def preview(request, layer_slug):
    """Home page for layers.

    :param request: The web request.
    :param layer_slug: The layer
    """
    layer = get_object_or_404(Layer, slug=layer_slug)

    layer_path = shapefile_path(layer.name)
    map_buffer = render_layers([layer_path])
    response = HttpResponse(map_buffer.data(), content_type='png')

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
