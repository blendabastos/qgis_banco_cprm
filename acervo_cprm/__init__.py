# -*- coding: utf-8 -*-
"""
Acervo SIG - CPRM: baixa camadas vetoriais do portal GEOSGB direto no QGIS.
"""


def classFactory(iface):
    from .plugin import PluginAcervoCPRM
    return PluginAcervoCPRM(iface)
