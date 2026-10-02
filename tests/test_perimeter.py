"""Rule and decision tests use controlled labels; these do not measure AI accuracy."""
import json
import tempfile
import unittest

import numpy as np

from jailwatch.detector import temporal_bird_match
from jailwatch.events import EventStore
from jailwatch.pipeline import Pipeline
from jailwatch.rules import Candidate, RuleEngine
from test_core import config,box


def perimeter_config():
    c=config(); c.crossing_direction='both'
    c.fence_zone=[[.3,.2],[.7,.2],[.7,.9],[.3,.9]]
    return c


class PerimeterTests(unittest.TestCase):
    def cross(self, r, points):
        return [event for i,x in enumerate(points) for event in r.crossing([box(x)],1+i*.04)]

    def test_bidirectional_crossings_and_independent_cooldown(self):
        c=perimeter_config(); c.cooldown_seconds=8
        incoming=self.cross(RuleEngine(c),[.38,.42,.46,.5,.54,.58])[0]
        outgoing=self.cross(RuleEngine(c),[.60,.56,.52,.48,.44,.40])[0]
        self.assertEqual(incoming.direction,'outside_to_inside')
        self.assertEqual(outgoing.direction,'inside_to_outside')
        r=RuleEngine(c); r.emitted(incoming.cooldown_key,1)
        self.assertFalse(r.permitted(incoming.cooldown_key,2))
        self.assertTrue(r.permitted(outgoing.cooldown_key,2))

    def test_outward_only_rejects_inward_and_accepts_outward(self):
        c=perimeter_config(); c.crossing_direction='inside_to_outside'
        self.assertEqual(self.cross(RuleEngine(c),[.38,.42,.46,.5,.54]),[])
        self.assertEqual(len(self.cross(RuleEngine(c),[.6,.56,.52,.48,.44])),1)

    def test_stationary_person_requires_dwell_and_reconfirms_after_gap(self):
        r=RuleEngine(perimeter_config()); events=[]
        for t in (0,.5,1,1.5,2): events+=r.person_movement([(.36,.3,.44,.65)],t)
        self.assertEqual([e.kind for e in events],['person_near_fence'])
        self.assertEqual(r.person_movement([(.36,.3,.44,.65)],2.5),[])
        r.person_movement([],5)
        self.assertEqual(r.person_movement([(.36,.3,.44,.65)],5.5),[])

    def test_person_context_is_local_past_and_on_origin_side(self):
        r=RuleEngine(perimeter_config())
        candidate=self.cross(r,[.38,.42,.46,.5,.54])[0]
        r.person_movement([(.34,.3,.42,.65)],.8)
        self.assertTrue(r.person_context(candidate)['nearby_person'])
        for t,person in [(1.5,(.34,.3,.42,.65)),(-4,(.34,.3,.42,.65)),(.8,(.57,.3,.64,.65)),(.8,(.34,.8,.42,.88))]:
            other=RuleEngine(perimeter_config()); other.person_movement([person],t)
            self.assertFalse(other.person_context(candidate)['nearby_person'])

    def test_fence_ignore_zone_and_reset_remove_context(self):
        c=perimeter_config(); c.ignore_zones=[c.fence_zone]
        r=RuleEngine(c)
        for t in (0,1,2,3): self.assertEqual(r.person_movement([(.34,.3,.42,.65)],t),[])
        r.reset(); self.assertEqual(len(r.person_observations),0)

    def test_semantic_bird_association_uses_matching_source_time(self):
        trail=[(1,.4,.5),(1.1,.5,.5),(1.2,.6,.5)]
        self.assertTrue(temporal_bird_match(trail,[(1.1,(.48,.48,.52,.52))]))
        self.assertFalse(temporal_bird_match(trail,[(.5,(.48,.48,.52,.52))]))
        self.assertFalse(temporal_bird_match(trail,[(1.1,(.2,.2,.25,.25))]))
        self.assertFalse(temporal_bird_match([(1,.4,.5),(2,.6,.5)],[(1.5,(.48,.48,.52,.52))]))

    def test_bird_overrides_person_context_and_custom_object(self):
        with tempfile.TemporaryDirectory() as d:
            p=Pipeline(perimeter_config(),None,EventStore(d))
            candidate=self.cross(p.rules,[.38,.42,.46,.5,.54])[0]
            p.rules.person_movement([(.34,.3,.42,.65)],.8)
            self.assertTrue(p.rules.person_context(candidate)['nearby_person'])
            p.bird_observations.append((1.08,box(.46)))
            self.assertIsNone(p._candidate_result(candidate,np.zeros((100,100,3),np.uint8),'thrown_object'))
            self.assertEqual(p.suppressed_birds,1); self.assertEqual(p.store.list(),[])

    def test_unknown_silent_review_persists_without_alarm_and_custom_class_notifies(self):
        with tempfile.TemporaryDirectory() as d:
            c=perimeter_config(); c.unknown_crossing_policy='review'
            p=Pipeline(c,None,EventStore(d)); image=np.zeros((100,100,3),np.uint8)
            candidate=self.cross(p.rules,[.38,.42,.46,.5,.54])[0]
            p.rules.person_movement([(.34,.3,.42,.65)],.8)
            event=p._candidate_result(candidate,image,None)
            self.assertFalse(event['notify']); self.assertTrue(event['details']['nearby_person'])
            self.assertEqual(p.store.list(notifications_only=True),[])
            self.assertEqual(json.loads(p.store.list()[0]['details'])['direction'],'outside_to_inside')
            event=p._candidate_result(candidate,image,'thrown_object')
            self.assertTrue(event['notify']); self.assertEqual(len(p.store.list(notifications_only=True)),1)

    def test_bad_direction_policy_and_fence_polygon_rejected(self):
        for name,value in [('crossing_direction','up'),('unknown_crossing_policy','ignore'),('fence_dwell_seconds',-1),('fence_zone',[[0,0],[1,1]])]:
            c=perimeter_config(); setattr(c,name,value)
            with self.assertRaises(ValueError): c.validate()
