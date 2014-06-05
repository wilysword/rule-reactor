from dateutil.parser import parse as parse_date
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.shortcuts import render, redirect

from .forms import BulkResolveForm
from .models import Rule, Occurrence


@login_required
def index(request):
    if request.user.is_superuser:
        rules_qs = Rule.objects.all()
    else:
        rules_qs = Rule.objects.for_customer(request.user.customer)
    rules_qs.query.select_related = False
    tables = ContentType.objects.filter(pk__in=rules_qs.values('table_id').query)
    models = []
    for table in tables:
        model = table.model_class()
        mname = '{}.{}'.format(table.app_label, table.model)
        if not request.user.is_superuser and hasattr(model, 'with_perms'):
            model_qs = model.with_perms(request.user).values('pk')
            q = Q(Q(occurrence__isnull=True) | Q(occurrence__object_id__in=model_qs.query),
                  table_id=table.pk, occurrence__resolution_date__isnull=True)
        else:
            q = Q(table_id=table.pk)
        rules = rules_qs.filter(q).annotate(unresolved=Count('occurrence'))
        models.append((mname, rules))
    return render(request, 'rule_reactor/index.html', {'model_rules': models})


@login_required
def occurrences(request, archive=False):
    if 'resolve' in request.POST:
        form = BulkResolveForm(request.POST)
        if form.is_valid():
            form.cleaned_data['occurrences'].resolve(request.user, form.cleaned_data['resolution_message'])
            return redirect('rules:occurrence-list')
    else:
        form = BulkResolveForm()

    q = Q(resolution_date__isnull=not archive)
    if not request.user.is_superuser:
        q &= Q(Q(rule__customer__isnull=True) | Q(rule__customer=request.user.customer))

    rules = request.GET.getlist('rule')
    if rules:
        q &= Q(rule_id__in=rules)

    models = request.GET.getlist('model')
    try:
        models = [ContentType.objects.get_by_natural_key(*m.split('.')).pk for m in models]
    except:
        models = None
    if models:
        q &= Q(rule__table_id__in=models)

    start = request.GET.get('start')
    if start:
        q &= Q(creation_date__gte=parse_date(start))

    end = request.GET.get('end')
    if end:
        q &= Q(creation_date__lte=parse_date(end))

    occurrences = Occurrence.objects.filter(q).select_related('rule', 'rule__table')
    rule_count = 0
    tables = {}
    for occ in occurrences:
        mname = '{0.app_label}.{0.model}'.format(occ.rule.table)
        if mname not in tables:
            tables[mname] = {}
        if occ.rule_id not in tables[mname]:
            tables[mname][occ.rule_id] = (occ.rule, {})
            rule_count += 1
        tables[mname][occ.rule_id][1][occ.pk] = occ
    context = {
        'tables': tables,
        'rule_count': rule_count,
        'bulk_resolve': not archive and rule_count == 1,
        'archive': archive,
        'form': form
    }
    if len(tables) == 1:
        for t in tables:
            context['table'] = t
    if rule_count == 1:
        for t in tables:
            for pk, (rule, _) in tables[t].items():
                context['rule'] = rule
    return render(request, 'rule_reactor/occurrences.html', context)
