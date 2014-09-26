from django.conf.urls import patterns, url
from layers.views import index, calculate, detail, preview

urlpatterns = patterns(
    '',
    url(r'^$', index, name='index'),
    url(r'calculate/$', calculate, name='calculate'),
    url(r'^(?P<layer_slug>[\w\-]+)/$', detail, name='detail'),
    url(r'preview/(?P<layer_slug>[\w\-]+)/$', preview, name='preview'),
)
