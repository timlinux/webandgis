import sys
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
from subprocess import call
from django.contrib.auth.decorators import login_required

from PyQt4.QtCore import QCoreApplication, QSize
from PyQt4.QtGui import QImage, QPainter, QColor
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

    context = {'layers': layers, 'providers': providers, 'sizes': sizes}
    return render(request, 'layers/index.html', context)


def preview(request, layer_slug):
    """Home page for layers.

    :param request: The web request.
    :param layer_slug: The layer
    """
    layer = get_object_or_404(Layer, slug=layer_slug)

    layer_path = os.path.join(
        settings.MEDIA_ROOT, 'layers', layer.slug, 'raw')
    map_layer = QgsVectorLayer(layer_path, layer.name, 'ogr')
    QgsMapLayerRegistry.instance().addMapLayer(map_layer)
    layer_uri = '/tmp/canvas.png'

    # create image
    image = QImage(QSize(800, 600), QImage.Format_ARGB32_Premultiplied)

    # set image's background color
    color = QColor(255, 255, 255)
    image.fill(color.rgb())

    # create painter
    p = QPainter()
    p.begin(image)
    p.setRenderHint(QPainter.Antialiasing)

    renderer = QgsMapRenderer()

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
    # save image
    image.save(layer_uri, 'png')
    with open(layer_uri, 'rb') as f:
        response = HttpResponse(f.read(), content_type='png')

    return response


def detail(request, layer_slug):
    """Ariel must document his code!"""
    layer = get_object_or_404(Layer, slug=layer_slug)

    #get GeoJSON file
    layer_folder = os.path.join(settings.MEDIA_URL, 'layers', layer_slug)
    geometry_json = os.path.join(layer_folder, 'raw', 'geometry.json')
    context = {'layer': layer}
    context['geojson'] = geometry_json

    return render(request, 'layers/detail.html', context)


def get_layer_data(layer_name):
    layer = Layer.objects.get(name=layer_name)
    layer_path = os.path.join(settings.MEDIA_ROOT, 'layers', layer.slug, 'raw')
    os.chdir(layer_path)
    filename = glob.glob('*.shp')[0]
    layer_file = os.path.join(layer_path, filename)
    return read_layer(layer_file)


@login_required(redirect_field_name='next')
def calculate(request):
    """Calculates the buildings affected by flood.
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

    call(['ogr2ogr', '-f', 'GeoJSON',
          output, impact_file.filename])

    impact_geojson = os.path.join(settings.MEDIA_URL, 'layers', 'impact.json')

    context = impact_file.keywords
    context['geojson'] = impact_geojson
    context['user'] = request.user

    return render(request, 'layers/calculate.html', context)
