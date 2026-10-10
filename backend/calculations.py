from __future__ import annotations
from backend.schemas import Book, Item, Room, Totals, Review

FT2_PER_M2 = 10.7639104167

def rectangular_room(length: float, width: float, height: float) -> tuple[float,float]:
    if min(length,width,height) <= 0:
        raise ValueError('Dimensions must be positive')
    return round(length * width, 4), round(2*height*(length + width), 4)

def polygon_area(points: list[tuple[float,float]]) -> float:
    if len(points) < 3:
        raise ValueError('Polygon needs >= 3 corners')
    return abs(sum(points[i][0]*points[(i+1)%len(points)][1] - points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points)))) / 2

import math

def populate_room(room: Room, polygon_points: list[tuple[float,float]] | None = None) -> Room:
    room.floor_area_m2 = room.wall_area_m2 = room.floor_area_ft2 = room.wall_area_ft2 = None
    if room.shape == 'rectangular' and all(x is not None for x in (room.length_m,room.width_m,room.height_m)):
        floor, wall = rectangular_room(room.length_m,room.width_m,room.height_m)
        room.floor_area_m2,room.wall_area_m2 = floor,wall
        room.floor_area_ft2,room.wall_area_ft2 = round(floor*FT2_PER_M2,3),round(wall*FT2_PER_M2,3)
    elif room.shape == 'irregular' and polygon_points and len(polygon_points) >= 3:
        floor = round(polygon_area(polygon_points), 4)
        room.floor_area_m2 = floor
        room.floor_area_ft2 = round(floor*FT2_PER_M2, 3)
        if room.height_m and room.height_m > 0:
            perimeter = sum(
                math.hypot(polygon_points[(i+1)%len(polygon_points)][0] - polygon_points[i][0],
                           polygon_points[(i+1)%len(polygon_points)][1] - polygon_points[i][1])
                for i in range(len(polygon_points))
            )
            wall = round(perimeter * room.height_m, 4)
            room.wall_area_m2 = wall
            room.wall_area_ft2 = round(wall*FT2_PER_M2, 3)
    return room

def calculate_totals(books: list[Book], items: list[Item], currency: str) -> Totals:
    active_books = [b for b in books if not b.excluded]
    active_items = [i for i in items if not i.excluded]
    def price_sum(prices):
        return round(sum(p.amount for p in prices if p.amount is not None and p.currency == currency),2)
    shelf_run = sum(b.spine_thickness_cm for b in active_books if b.spine_thickness_cm is not None)
    has_thickness = len(active_books)>0 and all(b.spine_thickness_cm is not None for b in active_books)
    lows = [i.replacement_cost.low for i in active_items if i.replacement_cost.low is not None and i.replacement_cost.currency == currency]
    highs = [i.replacement_cost.high for i in active_items if i.replacement_cost.high is not None and i.replacement_cost.currency == currency]
    return Totals(book_count=len(active_books),books_identified=sum(b.status=='identified' for b in active_books),
        books_unidentified=sum(b.status!='identified' for b in active_books), shelf_run_m=round(shelf_run/100,3) if has_thickness else None,
        books_replacement_cost=price_sum(b.replacement_cost for b in active_books if b.status!='needs_appraisal'),
        books_used_value=price_sum(b.used_value for b in active_books if b.status!='needs_appraisal'),
        items_replacement_cost_low=round(sum(lows),2),items_replacement_cost_high=round(sum(highs),2),
        excluded_from_totals=sum(b.excluded for b in books)+sum(i.excluded for i in items)+sum(b.status=='needs_appraisal' for b in active_books)+sum(i.status=='needs_appraisal' for i in active_items),
        unpriced_books=sum(b.status=='needs_appraisal' or b.replacement_cost.amount is None or b.used_value.amount is None for b in active_books),
        unpriced_items=sum(i.replacement_cost.low is None for i in active_items),currency=currency)

def make_review(books:list[Book],items:list[Item],room:Room) -> list[Review]:
    issues = []
    def add(identifier,reason): issues.append(Review(ref_id=identifier,reason=reason))
    for b in books:
        if b.excluded: continue
        if not b.title: add(b.id,'Unreadable spine / unidentified book')
        if b.status=='needs_appraisal': add(b.id,'Rare, signed, first-edition claim or appraisal requested')
        if b.id_confidence < .75 and b.title: add(b.id,'Ambiguous identification / insufficient title confidence')
        if b.spine_height_cm is None or b.spine_thickness_cm is None: add(b.id,'No defensible metric scale or dimensions unavailable')
        if b.replacement_cost.amount is None: add(b.id,'Replacement market price unverified')
        if b.used_value.amount is None: add(b.id,'Used-market price unverified')
    for i in items:
        if i.excluded: continue
        if i.status=='needs_appraisal': add(i.id,'Original artwork or item value needs human appraisal')
        if i.replacement_cost.low is None: add(i.id,'Non-book replacement valuation unavailable')
    if room.floor_area_m2 is None: add('room','Room scale/geometry not established')
    unique=[];seen=set()
    for r in issues:
        key=(r.ref_id,r.reason)
        if key not in seen: seen.add(key); unique.append(r)
    return unique
