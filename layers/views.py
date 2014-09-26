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

import qgis
from PyQt4.QtCore import QCoreApplication, QSettings, QSize
from PyQt4.QtGui import QApplication
from qgis.core import (
    QgsApplication,
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsMapLayer,
    QgsRectangle
    )
from qgis.gui import QgsMapCanvasLayer, QgsMapCanvas

def index(request):
    """Home page for layers.

    :param request: The web request.
    """
    QCoreApplication.setOrganizationName('QGIS')
    QCoreApplication.setOrganizationDomain('qgis.org')
    QCoreApplication.setApplicationName('QGIS2InaSAFETesting')

    #noinspection PyPep8Naming
    gui_flag = False
    app = QApplication(argv, True)
    qgis_app = QgsApplication(sys.argv, gui_flag)

    # Make sure QGIS_PREFIX_PATH is set in your env if needed!
    qgis_app.initQgis()

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
    QCoreApplication.setOrganizationName('QGIS')
    QCoreApplication.setOrganizationDomain('qgis.org')
    QCoreApplication.setApplicationName('QGIS2InaSAFETesting')

    #noinspection PyPep8Naming
    gui_flag = False
    app = QApplication(None, True)
    qgis_app = QgsApplication(sys.argv, gui_flag)

    # Make sure QGIS_PREFIX_PATH is set in your env if needed!
    qgis_app.initQgis()

    layer_path = os.path.join(
        settings.MEDIA_ROOT, 'layers', layer.slug, 'raw')
    map_layer = QgsVectorLayer(layer_path, layer.name, 'ogr')
    canvas = QgsMapCanvas(None)
    canvas.resize(QSize(400, 400))
    canvas_layer = QgsMapCanvasLayer(map_layer)
    canvas.setLayerSet([canvas_layer])
    canvas.zoomToFullExtent()
    canvas.refresh()

    layer_uri = '/tmp/canvas.png'
    canvas.saveAsImage(layer_uri)
    with open(layer_uri, 'rb') as f:
        response = HttpResponse(f.read(), mimetype='png')

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
