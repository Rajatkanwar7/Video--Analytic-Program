# Two-way perimeter monitoring

## Calibrate every fixed camera

Draw OUTSIDE on the physical outside of the jail and INSIDE on the physical inside. Leave a narrow gap at the wall if needed; these polygons cannot overlap. Both directions means the same calibrated polygons are used for inward and outward tracks. It does not swap the camera's perspective.

Draw the optional FENCE polygon over the ground area where a person's **feet** appear near the fence on either side. It can overlap INSIDE/OUTSIDE. Avoid drawing only the top of the wall: foot-based occupancy will not work there. The default fence dwell is two source-video seconds. An occluded person or invisible feet may not produce this warning. IGNORE regions exclude irrelevant motion and person occupancy. Redraw zones after moving or zooming the camera.

In Edit → AI settings, select `both`, `outside_to_inside` or `inside_to_outside`. Existing VMS inventories without a direction setting migrate to `both`; legacy single-camera JSON retains its historical inward-only default. Confirm this during upgrade commissioning.

## Decision sequence

1. Background motion produces small-object observations, tracked on each available decoded frame. Warmup, frame gaps, large scene changes and ignored areas reset or exclude tracks.
2. A candidate needs a measured origin in one zone and an end in the opposite zone, sufficient points, speed and displacement within the configured duration. Each direction has its own camera-wide cooldown. One continuous track fires at most once.
3. The AI checks the crossing image and up to five time-sampled contextual crops, preserving the launch sample and including later observations. Visual bird evidence from any reviewed frame vetoes a custom-object match. Full-frame bird sightings can also veto a crossing when they align with the measured path at their own source time; stale positions are not extrapolated.
4. Recognized person motion is filtered from the thrown-object detector. Person movement and fence dwell have their own alert rules.
5. When an actual candidate exists, the system searches recent **pre-launch** person observations. A person's feet must be in the fence area on the origin side and the observed launch point must be close to that person's box. The default context window is three seconds and the distance is 0.12 in normalized image coordinates. These are perspective-dependent image distances, not metres.
6. A matched person gives an **elevated review priority** and saved source-time evidence. It is not proof that the person threw anything and is not a calibrated probability. A bird veto still wins.

## Notification policies

| Result | Alarm behavior |
| --- | --- |
| Bird recognized on the candidate path | No throw event or throw notification; suppressed-bird count increases. |
| Person recognized as the moving blob | Suppressed from thrown-object events; independent person rules still apply. |
| Custom `thrown_object` match and no bird/person veto | Suspected crossing saved and notified; human review still required. |
| Unclassified crossing; default policy | Saved and notified as a suspected throw requiring review. |
| Unclassified crossing; “Save unknown crossings silently” selected | Saved in Alarms as Silent review, with snapshot/path; no sound or red alert banner. Nearby-person context does not override this policy. |
| “Require custom thrown_object class” enabled | Unknown candidates are suppressed entirely; a model with that class is required. |
| Sustained person occupancy in FENCE | Separate person-near-fence warning. No throw is established. |

Silent review can reduce bird false alarms but can also silence real packages. The default generic YOLO11n recognizes people and birds; it has no trained `thrown_object` class. Therefore, silent review with generic weights can silence all unknown-object crossings. Do not confuse a low alarm count with high detection accuracy.

## Why there is no “bird flight equals X” shortcut

Birds can glide and follow smooth paths without visible wingbeats. Other birds flap faster than ordinary CCTV frame rates can resolve. Flight-path shape and apparent wing motion are useful review cues but are not a reliable species test. The implementation uses temporal visual classification, not a rule that labels every curved or straight path as a bird or a package. Tiny, blurred or occluded objects may remain ambiguous.

Primary background: [Cornell Lab, wingbeat behavior](https://academy.allaboutbirds.org/singing-wings-behavior/) and [Ákos, Nagy and Vicsek, recorded gliding/soaring trajectories](https://arxiv.org/abs/0902.0312). No new bird behavior model has been trained in this release.

## Validate the real system

Record marked inward and outward trials, people standing/walking near the fence without throws, birds crossing in both directions (including gliding birds), insects, vegetation and night/rain footage. Review the full recordings. Measure event recall separately by direction, false audible alarms per hour, bird false-alarm rate, notification latency and frame/AI queue loss. Review silent events and suppressed false negatives as well as visible alarms. A successful software test does not establish those field metrics.

Keep a held-out set of complete incidents from different camera/day groups. Use the [training guide](TRAINING.md) for labels and custom-model training. Benchmark each added AI camera alongside recording load; default two concurrent AI cameras is a capacity guard, not a throughput promise. If queues overflow, reduce load or provide more suitable hardware before relying on alerts.
