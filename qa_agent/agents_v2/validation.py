from urllib.parse import urljoin
from ..evolution import canonical_url
from ..safety import check_action, target_url


def plan_issues(plan, pages, request=None):
    """Static errors; post-click DOM is checked by live validation, not guessed."""
    issues = {}
    by_url = {canonical_url(p['url']): p for p in pages}
    for flow in plan.flows:
        errors, page, changed = [], None, False
        meaningful = [s for s in flow.steps if s.action.startswith('assert_')
                      and not (s.action == 'assert_visible' and s.target.strip().lower() in {'body', 'html', '*'})]
        if not meaningful: errors.append('No meaningful outcome assertion; body visibility is insufficient')
        if flow.category in {'negative', 'boundary'} and not any(s.action in {'assert_text', 'assert_invalid'} for s in meaningful):
            errors.append('Negative/boundary test needs validation feedback or native invalidity assertion')
        last_action = max((i for i,s in enumerate(flow.steps) if s.action in {'fill','select_option','click'}), default=-1)
        if last_action >= 0 and not any(i > last_action and s in meaningful for i,s in enumerate(flow.steps)):
            errors.append('No outcome assertion after the interaction')
        for step in flow.steps:
            if request:
                try:
                    check_action(step, request.allow_interactions)
                    if step.action == 'navigate': target_url(request.url, step.target, request.navigation_origins)
                except ValueError as exc: errors.append(str(exc))
            if step.action == 'navigate':
                url = urljoin(request.url if request else flow.steps[0].target, step.target)
                page, changed = by_url.get(canonical_url(url)), False
                continue
            if step.action in {'assert_text', 'assert_url'} and not step.value.strip(): errors.append('Empty expected text or URL')
            if page and not changed and step.target:
                local = next((e for e in page.get('elements',[]) if e['selector'] == step.target), None)
                other = any(e['selector'] == step.target for p in pages if p is not page for e in p.get('elements',[]))
                if not local and other: errors.append(f'Selector belongs to another page: {step.target}')
                if local and step.action == 'fill' and local['tag'] not in {'input','textarea'}:
                    errors.append(f'fill cannot operate on {local["tag"]}: {step.target}; use select_option for dropdowns')
                if local and step.action == 'select_option' and local['tag'] != 'select': errors.append('select_option requires select element')
            if step.action == 'click': changed = True
        if errors: issues[flow.id] = list(dict.fromkeys(errors))
    return issues


def compact_results(results):
    return [{**{k:r.get(k) for k in ('flow_id','status','failed_step','failure_kind','error','classification')},
             'failure_snapshot': {k:r.get('failure_snapshot',{}).get(k) for k in ('url','elements','text')}} for r in results]
