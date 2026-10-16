"""Strict replay structure and integer comparison, bounded float-only tolerance."""
import math


def compare_engine_state(actual, expected, abs_tol=1e-9):
    if not math.isfinite(abs_tol) or abs_tol < 0:
        raise ValueError('Tolerance must be finite and nonnegative')
    differences = []
    max_abs = 0.0

    def walk(a, b, path):
        nonlocal max_abs
        if type(a) is not type(b):
            differences.append({'path':path,'kind':'type','actual_type':type(a).__name__,
                                'expected_type':type(b).__name__,'within_tolerance':False})
        elif isinstance(a, dict):
            if a.keys() != b.keys():
                differences.append({'path':path,'kind':'keys','actual':sorted(a),
                                    'expected':sorted(b),'within_tolerance':False})
            for key in a.keys() & b.keys():walk(a[key],b[key],path+'.'+key)
        elif isinstance(a, list):
            if len(a) != len(b):
                differences.append({'path':path,'kind':'length','actual':len(a),
                                    'expected':len(b),'within_tolerance':False})
            for index,(x,y) in enumerate(zip(a,b)):walk(x,y,path+f'[{index}]')
        elif isinstance(a,float):
            finite=math.isfinite(a) and math.isfinite(b)
            if a != b or not finite:
                delta=abs(a-b) if finite else None
                if delta is not None:max_abs=max(max_abs,delta)
                differences.append({'path':path,'kind':'float','actual':a if finite else repr(a),
                                    'expected':b if finite else repr(b),'abs_diff':delta,
                                    'within_tolerance':finite and delta<=abs_tol})
        elif a != b:
            differences.append({'path':path,'kind':'exact_value','actual':a,'expected':b,
                                'within_tolerance':False})

    walk(actual,expected,'state')
    return {'exact':not differences,'bounded_float':all(d['within_tolerance'] for d in differences),
            'float_abs_tolerance':abs_tol,'max_abs_float_difference':max_abs,'differences':differences}
