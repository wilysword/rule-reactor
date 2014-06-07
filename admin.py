from django.contrib import admin
from reversion import VersionAdmin
from .models import Condition, Rule, Occurrence


class ConditionAdmin(admin.StackedInline):
    model = Condition

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'apply_to':
            kwargs['choices'] = Condition._APPS
        return super(ConditionAdmin, self).formfield_for_choice_field(db_field, request, **kwargs)

    def queryset(self, request):
        return Condition.objects._all()


class RuleAdmin(VersionAdmin):
    inlines = [ConditionAdmin]


admin.site.register(Rule, RuleAdmin)
admin.site.register(Occurrence)
