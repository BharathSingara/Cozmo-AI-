"""Frame-to-frame homography tracking. Refuse long-range similarity-only deduplication."""
import cv2, numpy as np
from backend.vision import _iou

def estimate_transform(previous,current):
    orb=cv2.ORB_create(1000)
    k1,d1=orb.detectAndCompute(cv2.cvtColor(previous,cv2.COLOR_BGR2GRAY),None)
    k2,d2=orb.detectAndCompute(cv2.cvtColor(current,cv2.COLOR_BGR2GRAY),None)
    if d1 is None or d2 is None or len(k1)<12 or len(k2)<12:return None
    matches=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1,d2,k=2)
    good=[m for pair in matches if len(pair)==2 for m,n in [pair] if m.distance<.72*n.distance]
    if len(good)<12:return None
    src=np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst=np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    matrix,mask=cv2.findHomography(src,dst,cv2.RANSAC,4.0)
    if matrix is None or mask is None or int(mask.sum())<10:return None
    return matrix

def transform_bbox(bbox,matrix):
    x1,y1,x2,y2=bbox
    pts=np.float32([[x1,y1],[x2,y1],[x2,y2],[x1,y2]]).reshape(-1,1,2)
    projected=cv2.perspectiveTransform(pts,matrix).reshape(-1,2)
    return [float(min(projected[:,0])),float(min(projected[:,1])),float(max(projected[:,0])),float(max(projected[:,1]))]

def match_proposals(previous_boxes:list[list[int]],new_boxes:list[list[int]],matrix):
    """Unique one-to-one matches, matching only geometrically-supported correspondences."""
    if matrix is None:return {}
    pairs=[]
    for pi,box in enumerate(previous_boxes):
        transformed=transform_bbox(box,matrix)
        for ni,other in enumerate(new_boxes):
            overlap=_iou(transformed,other)
            if overlap>.30:pairs.append((overlap,pi,ni))
    usedp=set();usedn=set();match={}
    for score,pi,ni in sorted(pairs,reverse=True):
        if pi not in usedp and ni not in usedn:
            match[ni]=pi;usedp.add(pi);usedn.add(ni)
    return match
