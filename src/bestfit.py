import bisect

def bestfit(ref, mapping], /):
    """Finds best fitting entry in mapping.

    Positional parameters:
        ref - reference value, must be numeric
        mapping - sorted list of tuples (x_i, n_i) where n_i is numeric
    Returns:
        A tuple (x_k, delta) such that x_k belongs to k-th element of mapping,
        and delta = n_i - ref. The point is that absolute value of delta 
        is minimal across all mapping.
    """
    i = bisect.bisect(mapping, ref, key=lambda x: x[1])
    if i == 0:
        diff = [
            (mapping[0][0], mapping[0][1] - ref),
            (mapping[1][0], mapping[1][1] - ref),
        ]
    elif i == len(mapping) - 1:
        diff = [
            (mapping[-2][0], mapping[-2][1] - ref),
            (mapping[-1][0], mapping[-1][1] - ref),
        ]
    else:
        diff = [
            (mapping[i-1][0], mapping[i-1][1] - ref),
            (mapping[i  ][0], mapping[i  ][1] - ref),
            (mapping[i+1][0], mapping[i+1][1] - ref),
        ]
    return min(diff, key=lambda x: abs(x[1]))
