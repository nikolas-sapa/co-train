import pytest

from bench import contamination as C


NONFINITE = [float('nan'), float('inf'), float('-inf')]
BIRD_CASES = [(0.52, 0.4, (0.44, 0.60)), (0.80, 1e-6, (0.72, 0.88))]


@pytest.mark.parametrize('value', NONFINITE, ids=['nan', 'posinf', 'neginf'])
@pytest.mark.parametrize('field', ['control_auc', 'control_p'])
@pytest.mark.parametrize('bird_auc,bird_p,bird_ci', BIRD_CASES, ids=['pass', 'fail'])
def test_nonfinite_control_cannot_grant_verdict(value, field, bird_auc, bird_p, bird_ci):
    controls = {'control_auc': 0.95, 'control_p': 1e-6}
    controls[field] = value
    assert C.decide_verdict(**controls, bird_auc=bird_auc, bird_p=bird_p,
                            bird_ci=bird_ci) == 'INCONCLUSIVE'


@pytest.mark.parametrize('value', NONFINITE, ids=['nan', 'posinf', 'neginf'])
@pytest.mark.parametrize('field', ['bird_auc', 'bird_p', 'ci_lower', 'ci_upper'])
@pytest.mark.parametrize('bird_auc,bird_p,bird_ci', BIRD_CASES, ids=['pass', 'fail'])
def test_nonfinite_bird_reading_is_inconclusive(value, field, bird_auc, bird_p, bird_ci):
    if field == 'bird_auc':
        bird_auc = value
    elif field == 'bird_p':
        bird_p = value
    elif field == 'ci_lower':
        bird_ci = (value, bird_ci[1])
    else:
        bird_ci = (bird_ci[0], value)
    assert C.decide_verdict(control_auc=0.95, control_p=1e-6,
                            bird_auc=bird_auc, bird_p=bird_p,
                            bird_ci=bird_ci) == 'INCONCLUSIVE'


@pytest.mark.parametrize('value', NONFINITE, ids=['nan', 'posinf', 'neginf'])
@pytest.mark.parametrize('group', ['pos', 'neg'])
@pytest.mark.parametrize('index', [0, 1, 2])
def test_auc_rejects_nonfinite_scores_in_either_group(value, group, index):
    groups = {'pos': [2.0, 3.0, 4.0], 'neg': [0.0, 0.5, 1.0]}
    groups[group][index] = value
    with pytest.raises(ValueError, match='finite'):
        C.auroc(groups['pos'], groups['neg'])


@pytest.mark.parametrize('pos,neg,expected', [
    ([2.0], [1.0], 1.0),
    ([1.0], [1.0], 0.5),
    ([1.0], [2.0], 0.0),
    ([1.0, 2.0], [0.0, 1.0], 0.875),
])
def test_finite_auc_contract(pos, neg, expected):
    assert C.auroc(pos, neg) == expected


@pytest.mark.parametrize('pos,neg', [([], [1.0]), ([1.0], []), ([], [])])
def test_empty_auc_groups_refused(pos, neg):
    with pytest.raises(ValueError, match='both groups non-empty'):
        C.auroc(pos, neg)


@pytest.mark.parametrize('control_auc,control_p,bird_auc,bird_p,bird_ci,expected', [
    (0.95, 1e-6, 0.52, 0.4, (0.44, 0.60), 'PASS'),
    (0.95, 1e-6, 0.80, 1e-6, (0.72, 0.88), 'FAIL'),
    (0.40, 0.9, 0.02, 0.9, (0.10, 0.60), 'INCONCLUSIVE'),
    (0.75, 0.009, 0.52, 0.4, (0.44, 0.60), 'PASS'),
    (0.749, 0.009, 0.52, 0.4, (0.44, 0.60), 'INCONCLUSIVE'),
    (0.95, 0.01, 0.52, 0.4, (0.44, 0.60), 'INCONCLUSIVE'),
    (0.95, 1e-6, 0.60, 0.4, (0.50, 0.65), 'INCONCLUSIVE'),
    (0.95, 1e-6, 0.65, 0.009, (0.51, 0.80), 'FAIL'),
    (0.95, 1e-6, 0.80, 0.01, (0.51, 0.88), 'INCONCLUSIVE'),
    (0.95, 1e-6, 0.80, 0.009, (0.50, 0.88), 'INCONCLUSIVE'),
])
def test_finite_verdict_thresholds(control_auc, control_p, bird_auc, bird_p, bird_ci, expected):
    assert C.decide_verdict(control_auc=control_auc, control_p=control_p,
                            bird_auc=bird_auc, bird_p=bird_p, bird_ci=bird_ci) == expected


@pytest.mark.parametrize('value', NONFINITE, ids=['nan', 'posinf', 'neginf'])
@pytest.mark.parametrize('field', [
    'control_positive', 'control_fresh', 'control_p', 'bird', 'bird_fresh', 'bird_p',
])
@pytest.mark.parametrize('bird_rates,bird_p', [
    ((0.02, 0.0), 0.5),
    ((0.4, 0.0), 1e-6),
], ids=['pass', 'fail'])
def test_nonfinite_binary_reading_is_inconclusive(value, field, bird_rates, bird_p):
    values = {
        'control_positive': 0.5, 'control_fresh': 0.0, 'control_p': 1e-4,
        'bird': bird_rates[0], 'bird_fresh': bird_rates[1], 'bird_p': bird_p,
    }
    values[field] = value
    assert C.decide_binary_verdict(
        control_rates=(values['control_positive'], values['control_fresh']),
        control_p=values['control_p'],
        bird_rates=(values['bird'], values['bird_fresh']),
        bird_p=values['bird_p'],
    ) == 'INCONCLUSIVE'


@pytest.mark.parametrize('control_rates,control_p,bird_rates,bird_p,expected', [
    ((0.5, 0.0), 1e-4, (0.4, 0.0), 1e-6, 'FAIL'),
    ((0.5, 0.0), 1e-4, (0.02, 0.0), 0.5, 'PASS'),
    ((0.02, 0.0), 0.5, (0.9, 0.0), 1e-9, 'INCONCLUSIVE'),
    ((0.10, 0.0), 0.009, (0.10, 0.0), 0.009, 'FAIL'),
    ((0.099, 0.0), 0.009, (0.4, 0.0), 1e-6, 'INCONCLUSIVE'),
    ((0.5, 0.0), 0.01, (0.4, 0.0), 1e-6, 'INCONCLUSIVE'),
    ((0.5, 0.0), 1e-4, (0.099, 0.0), 0.009, 'PASS'),
    ((0.5, 0.0), 1e-4, (0.4, 0.0), 0.01, 'PASS'),
])
def test_finite_binary_verdict_thresholds(control_rates, control_p, bird_rates, bird_p, expected):
    assert C.decide_binary_verdict(control_rates=control_rates, control_p=control_p,
                                   bird_rates=bird_rates, bird_p=bird_p) == expected
