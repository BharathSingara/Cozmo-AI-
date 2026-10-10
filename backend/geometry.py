"""Metric measurements only from an explicitly established, coplanar reference."""
from backend.schemas import Measurement

def metric_from_reference(target_px:float, reference_px:float, reference_cm:float,frame_ref:str,uncertainty_fraction:float=.1) -> Measurement:
    if min(target_px,reference_px,reference_cm)<=0: raise ValueError('Invalid reference / scale')
    if not 0<=uncertainty_fraction<=1: raise ValueError('Uncertainty must be between 0 and 1')
    value = round(target_px*reference_cm/reference_px,2)
    return Measurement(value=value,unit='cm',method='coplanar_known_width_pixel_ratio',frame_refs=[frame_ref],confidence=round(max(0,.8-uncertainty_fraction),2),uncertainty=round(value*uncertainty_fraction,2))

def book_spine_dimensions(bbox:list[int],frame_ref:str,reference_px:float|None,reference_cm:float|None):
    if reference_px is None or reference_cm is None: return None,None
    x1,y1,x2,y2=bbox
    w_px=abs(x2-x1); h_px=abs(y2-y1)
    # Long axis corresponds to spine height/length; short axis corresponds to spine thickness
    spine_len_px=max(h_px,w_px)
    spine_thk_px=min(h_px,w_px)
    return (metric_from_reference(spine_len_px,reference_px,reference_cm,frame_ref),
            metric_from_reference(spine_thk_px,reference_px,reference_cm,frame_ref))
