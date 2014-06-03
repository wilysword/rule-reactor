from django.contrib import admin
from reversion import VersionAdmin
from .models import Rule, Occurrence


class RuleAdmin(VersionAdmin):
    pass


admin.site.register(Rule, VersionAdmin)
admin.site.register(Occurrence)
