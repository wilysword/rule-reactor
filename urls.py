from django.conf.urls import patterns, url

urlpatterns = patterns(
    'rule_reactor.views',
    url('^$', 'index', name='index'),
    url('^occurrences/$', 'occurrences', name='occurrence-list'),
    url('^occurrences/archive/$', 'occurrences', name='occurrence-archive', kwargs={'archive': True}),
)
