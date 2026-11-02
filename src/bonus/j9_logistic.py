"""J9 weighted state solver; independent copy preserves frozen C0 source.

Preprocessing, L2 and convergence are identical to C0. Binary inverse-frequency
weights affect only the state objective/gradient/Hessian, never team heads.
"""
import numpy as np
from src.models.dataset import FeatureBlock
from src.models.tabular import transform, sigmoid

def fit_weighted_logistic(block, target, *, l2=.01, max_iterations=50, tolerance=1e-6, clip=8., balanced=False):
    if not isinstance(block, FeatureBlock):
        raise TypeError('A named observation block is required')
    values = np.asarray(block.values, dtype=float)
    y = np.asarray(target, dtype=float)
    if (values.ndim != 2 or len(values) < 2 or values.shape[1] != len(block.names)
            or np.isinf(values).any() or y.shape != (len(values),)
            or not np.isin(y, [0., 1.]).all() or len(np.unique(y)) != 2
            or not np.isfinite([l2, tolerance, clip]).all() or min(l2, tolerance, clip) <= 0
            or type(max_iterations) is not int or max_iterations < 1):
        raise ValueError('Invalid binary logistic training data/settings')
    weights = np.ones(len(y))
    if balanced:
        weights = np.where(y == 1, .5/y.mean(), .5/(1-y.mean()))
    missing = ~np.isfinite(values)
    location = np.zeros(values.shape[1])
    if not block.symmetric_team:
        for index in range(values.shape[1]):
            known = values[~missing[:, index], index]
            location[index] = float(np.median(known)) if len(known) else 0.
    filled = np.where(missing, location, values)
    # Odd team features must remain zero-centred: use RMS instead of centring.
    scale = np.sqrt(np.mean(filled**2, axis=0)) if block.symmetric_team else np.std(filled, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-6), scale, 1.)
    model = {'feature_names': list(block.names), 'symmetric_team': block.symmetric_team,
             'location': location.tolist(), 'scale': scale.tolist(), 'clip': float(clip),
             'l2': float(l2), 'calibrated': False}
    x = transform(block, model)
    coefficients = np.zeros(x.shape[1])
    penalty = np.ones(x.shape[1]) * l2
    if not block.symmetric_team:
        coefficients[0] = np.log(y.mean()/(1.-y.mean()))
        penalty[0] = 0.

    def objective(beta):
        logits = x @ beta
        return float(np.mean(weights*(np.logaddexp(0., logits)-y*logits)) + .5*np.sum(penalty*beta*beta))

    converged = False
    for iteration in range(max_iterations):
        p = sigmoid(x @ coefficients)
        gradient = x.T @ (weights*(p-y))/len(y) + penalty*coefficients
        if np.max(np.abs(gradient)) <= tolerance:
            converged = True
            break
        weight = weights*np.maximum(p*(1.-p), 1e-8)
        hessian = (x.T*weight) @ x/len(y) + np.diag(penalty+1e-8)
        step = np.linalg.solve(hessian, gradient)
        before = objective(coefficients)
        factor = 1.
        for _ in range(25):
            candidate = coefficients-factor*step
            if objective(candidate) <= before-1e-4*factor*float(gradient@step):
                coefficients = candidate
                break
            factor *= .5
        else:
            raise RuntimeError('Logistic optimization line search failed')
    final_gradient = x.T @ (weights*(sigmoid(x @ coefficients)-y))/len(y) + penalty*coefficients
    converged = converged or np.max(np.abs(final_gradient)) <= tolerance
    if not converged or not np.isfinite(coefficients).all():
        raise RuntimeError('Logistic model did not converge to the fixed tolerance')
    model.update(balanced=bool(balanced), class_weights=[float(weights[y==0][0]),float(weights[y==1][0])], coefficients=coefficients.tolist(), rows=len(y), positive_rows=int(y.sum()),
        iterations=iteration+1, converged=True, gradient_max=float(np.max(np.abs(final_gradient))),
        training_log_loss=float(np.mean(np.logaddexp(0., x@coefficients)-y*(x@coefficients))))
    return model

