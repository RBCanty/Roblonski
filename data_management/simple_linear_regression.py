from dataclasses import dataclass
from typing import Collection, Literal, Protocol


class Predictor[T](Protocol):
    def __call__(self, x_t: T, ptype: Literal[0,1] = ..., /) -> T:
        ...


@dataclass
class RegressionReport[T]:
    """ Container for the results of linear regression, storing key parameters without storing all X and Y data. """
    count: int
    average_x: T
    average_y: T
    sum_square_x: T
    sum_square_y: T
    sum_xy: T
    slope: T
    intercept: T
    slope_uncertainty: T
    intercept_uncertainty: T
    pearsons_r2: T
    mae: T
    ss_tot: T
    ss_res: T
    predictor: Predictor
    dof: int = 2

    def __call__(self, x_t: T) -> T:
        # Allows the 'report' to be called like a function on test data.
        return self.predictor(x_t, 0)[0]

    @property
    def rmse(self):
        """ Degree of freedom-scaled Root mean square error. """
        return (self.ss_res / (self.count - self.dof))**0.5

    def surprise(self, x_data: Collection[T], y_data: Collection[T]) -> list[tuple[int, T]]:
        """ Based on the uncertainty of prediction, it returns a list of (index, z_score offset)
        sorted from most to least surprising. """
        y_data_estimate = [self.predictor(xi) for xi in x_data]
        z_scores = [
            (i, abs(y_hat_i - yi) / s_y)
            for i, (xi, (y_hat_i, s_y), yi) in enumerate(zip(x_data, y_data_estimate, y_data))
        ]
        z_scores.sort(key=lambda x: x[-1], reverse=True)
        return z_scores


def slr[T](x: Collection[T], y: Collection[T], force_y_intercept: T = None):
    """ Simple linear regression for a collection of X and Y data. `force_y_intercept` can be used to specify the
    y-intercept; None will calculate this parameter freely. """
    if len(x) != len(y):
        raise ValueError(f"Data must have equivalent dimensions |x| = {len(x)}, |y| = {len(y)}")
    n = len(x)
    ex = sum(x)/n
    s_xx = sum([xi**2 for xi in x])
    dx = s_xx - n * ex * ex

    if force_y_intercept is None:
        use_y = y
    else:
        use_y = [_y - force_y_intercept for _y in y]

    ey = sum(use_y)/n
    s_yy = sum([yi**2 for yi in use_y])
    dy = s_yy - n * ey * ey

    s_xy = sum([xi*yi for xi, yi in zip(x, use_y)])
    dxy = s_xy - n*ex*ey

    dof = 2 if force_y_intercept is None else 1

    if force_y_intercept is None:
        slope = dxy / dx
        intercept = ey - slope*ex
    else:
        slope = s_xy / s_xx
        intercept = force_y_intercept

    ss_tot =  dy
    try:
        r2 = dxy**2 / (dx * dy)
    except ZeroDivisionError:
        print(f"ZDE on {x=} and {y=}")
        raise
    ss_res = dy*(1 - r2)  # s_ee

    sig_slope = ((ss_res / s_xx) / (n - dof)) ** 0.5
    sig_intercept = (dof - 1) * (sig_slope * (s_xx / n) ** 0.5)
    # note that "dof - 1" is either 0 or 1

    def predictor(x_t: T, ptype: Literal[0,1] = 1) -> tuple[T, T]:
        """ Estimates y(x_t) for a new data point.  Also provides a basis for predicting uncertainty/confidence bounds.
        As specified by ptype (what is being predicted), an example use would be "y(x_t) +/- t * basis" where t is a
        Student's t-value.  Confidence intervals seem to use the Variance of the mean response [ptype=0] (though I do
        not know why that is).

        :param x_t:
        :param ptype: 0 if "Given input x_t, on average, what is y(x_t)" (Variance of the mean response),
          1 if "Given a new input x_t, what is y(x_t)" (Variance of the predicted response)
        :return: (predicted value of y(x_t), basis for uncertainty/confidence bound)
        """
        scale = (ss_res / (n - dof))**0.5
        uncertainty_basis = scale * (ptype + (1/n) + (x_t - ex)**2 / dx )**0.5
        return slope*x_t + intercept, uncertainty_basis

    mae = sum([abs(yi - (slope*xi + intercept)) for xi, yi in zip(x, y)]) / n

    return RegressionReport(
        count=n,
        average_x=ex,
        average_y=ey,
        sum_square_x=s_xx,
        sum_square_y=s_yy,
        sum_xy=s_xy,
        slope=slope,
        intercept=intercept,
        slope_uncertainty=sig_slope,
        intercept_uncertainty=sig_intercept,
        pearsons_r2=r2,
        mae=mae,
        ss_tot=ss_tot,
        ss_res=ss_res,
        predictor=predictor,
        dof=dof
    )


if __name__ == '__main__':
    my_x_data = [0.0,2,4,6,8,10]
    my_y_data = [3*xi + 2 + 0.005*(1-xi)*(xi-4)*(xi+7) for xi in my_x_data]
    regression = slr(my_x_data, my_y_data)
    y_hat = [regression.predictor(xi) for xi in my_x_data]

    print("X Y Y_hat CI")
    for __x, __y, (est_y, d_y) in zip(my_x_data, my_y_data, y_hat):
        print(__x, __y, est_y, d_y)
    print("Slope Intercept R2 RMSE MAE")
    print(regression.slope, regression.intercept, regression.pearsons_r2, regression.rmse, regression.mae)

    shift = regression.surprise(my_x_data, my_y_data)

    print(shift)

    import math
    def rational_sampling(limit: int):
        fractions = { (n, d) for d in range(1, limit+1) for n in range(1,d+1) if math.gcd(n, d) == 1}
        yield 0
        for fraction in fractions:
            yield fraction[0] / fraction[1]

    print("\n".join([f"  {f}"for f in rational_sampling(2)]))
