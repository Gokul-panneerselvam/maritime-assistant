"""
Evaluation Test Harness for Maritime Operations Assistant.
Supports both live LangGraph execution and reproducible baseline/golden mock runs.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage

from ai_agent.src.evaluation.schemas import (
    BenchmarkQuestion,
    BenchmarkSummary,
    EvaluationResult,
)
from ai_agent.src.evaluation.dataset import get_benchmark_questions, get_benchmark_question_by_id
from ai_agent.src.evaluation.evaluators.composite_evaluator import CompositeEvaluator
from ai_agent.src.evaluation.trace import capture_trace
from ai_agent.src.utilities.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Golden Reference / Baseline Responses for Offline Evaluation & Testing
# =============================================================================
GOLDEN_REFERENCE_RESPONSES: Dict[str, Dict[str, Any]] = {
    "Q1": {
        "status": "SUCCESS",
        "executive_summary": (
            "MV Ocean Star's current voyage (VG-1042, Singapore SGSIN to Rotterdam NLRTM) is delayed by 55 hours "
            "(Original ETA: 2026-10-24 18:00 UTC; Revised ETA: 2026-10-27 01:00 UTC; Berth window was 2026-10-24 18:00 to 2026-10-25 05:00 local). "
            "The 55-hour delay is the cumulative result of 20 hours of en-route delay plus 35 hours of Maas anchorage waiting time "
            "due to terminal congestion at Rotterdam. Operations must confirm scheduled berthing with Van Dijk Shipping Agency, "
            "resolve Dutch customs manifest queries (INC-203), replenish mechanical seal kits under Harbourline Bulletin TB-26-14, "
            "and verify turnaround for subsequent voyage VG-1107."
        ),
        "confirmed_facts": [
            {
                "statement": "Main engine seawater cooling pump mechanical seal failure on 2026-10-06 resulted in 12 hours lost en route (INC-201, Confirmed).",
                "citations": ["INC-201", "noon_2026-10-06_ocean_star.txt"]
            },
            {
                "statement": "Weather deviation south of low-pressure system in Arabian Sea completed 13 Oct 22:00 UTC, losing 8 hours (noon_2026-10-14_ocean_star.txt).",
                "citations": ["noon_2026-10-14_ocean_star.txt"]
            },
            {
                "statement": "Vessel arrived at Rotterdam Maas Anchorage on 2026-10-25 14:00 UTC, exactly 20 hours after original ETA.",
                "citations": ["PC-7004", "agent_2026-10-25_rtm_anchorage.txt"]
            },
            {
                "statement": "Rotterdam terminal queue wait is 30-40 hours; berthing scheduled for 2026-10-27 01:00 UTC, accounting for 35 anchorage hours.",
                "citations": ["agent_2026-10-25_rtm_customs.txt", "PC-7004"]
            }
        ],
        "unverified_reports": [
            {
                "statement": "Dutch Customs raised a query on 3 manifest lines (INC-203, Under review). Port agent clarified this affects cargo release only, not berth allocation.",
                "source": "agent_2026-10-25_rtm_customs.txt",
                "citations": ["INC-203"]
            }
        ],
        "system_inferences": [
            {
                "deduction": "Total 55-hour delay is composed of 12h (mechanical) + 8h (weather) + 35h (anchorage queue) = 55 hours.",
                "rationale": "Missing the original 12h berth window pushed Ocean Star into the severe 30-40h yard congestion backlog at Rotterdam.",
                "supporting_citations": ["INC-201", "PC-7004"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Incident", "primary_id": "INC-201"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "PortCall", "primary_id": "PC-7004"}
        ]
    },

    "Q2": {
        "status": "SUCCESS",
        "executive_summary": (
            "Cross-fleet incident investigation for engine-cooling faults: "
            "1. On MV Ocean Star itself (V001): YES, once before on voyage VG-0981 (2026-08-02, 9.0h delay, INC-118, Confirmed). "
            "2. On same class (Meridian 8500): YES, on MV Ocean Pearl (V004, VG-0866 INC-077 10h; VG-1050 ~6h leak on 2026-10-02). "
            "Harbourline issued class alert TB-26-14 on 2026-10-09 for repeated pump seal failures. MV Coral Crest (V005) incident INC-041 was Dismissed. "
            "3. On same technical manager (Harbourline Ship Management): YES on Ocean Pearl (above), and MV Silver Tern (V006, INC-094 7h) "
            "which was formally clarified on 2026-10-21 as an auxiliary engine fresh water cooler leak, distinct from the Meridian 8500 pump seal defect."
        ),
        "confirmed_facts": [
            {
                "statement": "MV Ocean Star experienced a seawater cooling pump failure on voyage VG-0981 on 2026-08-02 (9.0h delay, INC-118, Confirmed).",
                "citations": ["INC-118", "agent_2026-08-17_sin_ocean_star_summary.txt"]
            },
            {
                "statement": "Sister vessel MV Ocean Pearl (V004, Meridian 8500) had confirmed engine cooling fault on voyage VG-0866 (INC-077, 10h delay) and pump seal leak on VG-1050.",
                "citations": ["INC-077", "noon_2026-10-02_ocean_pearl.txt"]
            },
            {
                "statement": "Harbourline Technical Bulletin TB-26-14 dated 2026-10-09 cites repeated pump seal failures on Meridian 8500 class vessels.",
                "citations": ["bulletin_2026-10-09_harbourline.txt"]
            },
            {
                "statement": "MV Silver Tern (V006, Harbourline) had INC-094 clarified as auxiliary engine cooler leak, not main engine pump seal defect.",
                "citations": ["INC-094", "agent_2026-10-21_correction_silver_tern.txt"]
            }
        ],
        "unverified_reports": [],
        "system_inferences": [
            {
                "deduction": "The seawater cooling pump mechanical seal failure is a documented recurring design defect specific to Meridian 8500 class operated by Harbourline.",
                "rationale": "Identified on both Ocean Star and Ocean Pearl prompting fleet bulletin TB-26-14.",
                "supporting_citations": ["INC-118", "INC-077", "bulletin_2026-10-09_harbourline.txt"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Incident", "primary_id": "INC-118"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "Incident", "primary_id": "INC-077"}
        ]
    },

    "Q3": {
        "status": "FALSE_PREMISE",
        "executive_summary": (
            "False assumption detected: MV Blue Horizon was NOT delayed at Hamburg last month. "
            "In fact, MV Blue Horizon (V002, Atlas 6000, Nordwave Marine) did not call at Hamburg last month at all. "
            "In September 2026 ('last month'), Blue Horizon executed voyage VG-0997 from Singapore to Antwerp (BEANR), "
            "berthing on schedule at Antwerp on 2026-09-16 08:00 UTC with 0 hours delay (PC-7008). "
            "Blue Horizon has zero recorded historical port calls at Hamburg; its first scheduled call to Hamburg is on voyage VG-1121 in late November."
        ),
        "confirmed_facts": [
            {
                "statement": "MV Blue Horizon completed voyage VG-0997 to Antwerp (BEANR) arriving 2026-09-16 08:00 UTC on schedule with 0h recorded delay.",
                "citations": ["PC-7008", "agent_2026-09-16_anr_blue_horizon.txt"]
            },
            {
                "statement": "MV Blue Horizon has zero recorded port calls at Hamburg in the operational database.",
                "citations": ["PC-7008"]
            }
        ],
        "unverified_reports": [],
        "system_inferences": [
            {
                "deduction": "The operator query either confused Hamburg with Antwerp (where Blue Horizon berthed on schedule 16 Sep) or referenced the upcoming November lineup.",
                "rationale": "Historical port calls show Antwerp, Singapore, and Shanghai calls, with no Hamburg calls.",
                "supporting_citations": ["PC-7008"]
            }
        ],
        "false_premises_detected": [
            {
                "user_assumption": "MV Blue Horizon was delayed at Hamburg last month",
                "grounded_reality": "MV Blue Horizon called at Antwerp (BEANR) on schedule with 0h delay on 16 Sep 2026; it has never called at Hamburg.",
                "citations": ["PC-7008", "agent_2026-09-16_anr_blue_horizon.txt"]
            }
        ],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "PortCall", "primary_id": "PC-7008"}
        ]
    },

    "Q4": {
        "status": "SUCCESS",
        "executive_summary": (
            "Ocean Star's current voyage (VG-1042) carries 267 confirmed containers actively on board across 5 affected customers: "
            "1. Kaimon Electronics: 90 containers (BK-50002: 60, BK-50007: 30); "
            "2. Halden Retail: 80 containers (BK-50001: 40, BK-50004: 25, BK-50009: 15); "
            "3. Petra Chemicals: 45 containers (BK-50006: 45); "
            "4. Lumio Home: 30 containers (BK-50005: 18, BK-50010: 12); "
            "5. Verdant Foods: 22 containers (BK-50003: 22). "
            "All promised delivery dates of 2026-10-28 are at risk or breached. "
            "Excluded: Northgate Auto (BK-50008, 50 containers) was Rolled to VG-1107 (0 on board). "
            "Brightline Apparel (BK-50011, 20 containers) was Cancelled (0 on board)."
        ),
        "confirmed_facts": [
            {
                "statement": "Voyage VG-1042 carries 267 active confirmed containers across Kaimon Electronics (90), Halden Retail (80), Petra Chemicals (45), Lumio Home (30), and Verdant Foods (22).",
                "citations": ["BK-50001", "BK-50002", "BK-50003", "BK-50004", "BK-50005", "BK-50006", "BK-50007", "BK-50009", "BK-50010"]
            },
            {
                "statement": "Northgate Auto booking BK-50008 (50 containers) has status Rolled to VG-1107 and has 0 containers on board VG-1042.",
                "citations": ["BK-50008"]
            },
            {
                "statement": "Brightline Apparel booking BK-50011 (20 containers) has status Cancelled and has 0 containers on board.",
                "citations": ["BK-50011"]
            }
        ],
        "unverified_reports": [
            {
                "statement": "Dutch Customs has queried 3 manifest lines (INC-203); specific customer bill of lading impact is pending agent notification.",
                "source": "agent_2026-10-25_rtm_customs.txt",
                "citations": ["INC-203"]
            }
        ],
        "system_inferences": [
            {
                "deduction": "All 5 customers with active cargo face delivery delays beyond promised 28 Oct date due to 27 Oct 01:00 UTC berthing and terminal turnaround.",
                "rationale": "Container discharge and yard operations require 24-48h post-berthing.",
                "supporting_citations": ["BK-50002", "PC-7004"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Booking", "primary_id": "BK-50002"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "Booking", "primary_id": "BK-50001"}
        ]
    },

    "Q5": {
        "status": "SUCCESS",
        "executive_summary": (
            "Analysis of 6 vessels due at Rotterdam (NLRTM) next week (Week 45, 2026-11-02 to 2026-11-08): "
            "Rank 1 (Certain / 100% Probability): MV Arctic Fern (VG-1088) — confirmed hull fouling speed loss (INC-221, 33h delay), "
            "revised ETA 04 Nov 15:00 arrives 23 hours after its berth window (03 Nov 04:00-16:00) closes. "
            "Rank 2 (Near-Certain / >95% Probability): MV Amber Coast (VG-1099) — slow steaming instruction (+18h) pushes arrival "
            "to 06 Nov 05:00, 8 hours after its berth window (05 Nov 09:00-21:00) expires. "
            "Rank 3 (High Risk): MV Northern Lark, MV Kestrel Bay, MV Celtic Dawn, MV Rio Verde — all subject to Rotterdam's 30-40h Maas anchorage "
            "yard congestion queue, which exceeds standard 12-hour allocated berth windows."
        ),
        "confirmed_facts": [
            {
                "statement": "MV Arctic Fern has confirmed 33h delay (INC-221, hull fouling), revised ETA 2026-11-04 15:00, missing berth window 03 Nov 04:00-16:00.",
                "citations": ["VG-1088", "INC-221"]
            },
            {
                "statement": "MV Amber Coast berth window is 2026-11-05 09:00 to 21:00 local; technical manager notice issued slow-steaming order (+18h impact).",
                "citations": ["VG-1099", "agent_2026-10-25_amber_coast_slow_steam.txt"]
            },
            {
                "statement": "Rotterdam port congestion is High with daily average wait times of 36 to 40 hours and 25 to 29 vessels waiting at anchor.",
                "citations": ["congestion.csv"]
            }
        ],
        "unverified_reports": [
            {
                "statement": "Port agent reports terminal waiting times expected to remain 30-40 hours into early November due to yard congestion.",
                "source": "agent_2026-10-25_rtm_queue.txt",
                "citations": []
            }
        ],
        "system_inferences": [
            {
                "deduction": "Arctic Fern is mathematically guaranteed to miss its berth window, while on-schedule vessels face severe risk from Maas anchorage backlog.",
                "rationale": "Transit delays plus 36-40h port waiting times exceed 12h berth tolerances.",
                "supporting_citations": ["VG-1088", "congestion.csv"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Voyage", "primary_id": "VG-1088"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "Voyage", "primary_id": "VG-1099"}
        ]
    },

    "Q6": {
        "status": "SUCCESS",
        "executive_summary": (
            "MV Arctic Fern (vessel_id V007, Atlas 6000, Nordwave Marine) on voyage VG-1088 from Singapore (SGSIN) to Rotterdam (NLRTM) "
            "is delayed by 33 hours (Original ETA: 2026-11-03 06:00 local; Revised ETA: 2026-11-04 15:00 local; Berth window was 03 Nov 04:00 to 16:00 local). "
            "The delay was caused by a confirmed 'Hull fouling / speed loss' incident reported on 2026-10-18 07:00 UTC by Nordwave Marine "
            "(INC-221, Confirmed, 33.0 attributed delay hours). Arriving 23h after its berth window closes, plus facing Rotterdam 30-40h yard backlog, "
            "berthing will slip into 5-6 November. Operations must reschedule the berth window with Van Dijk Shipping Agency, "
            "coordinate underwater hull inspection and cleaning with Nordwave Marine, and notify cargo customers (Halden Retail, Verdant Foods) of delivery breaches."
        ),
        "confirmed_facts": [
            {
                "statement": "MV Arctic Fern on voyage VG-1088 is delayed by 33 recorded hours, revising ETA to 2026-11-04 15:00 local.",
                "citations": ["VG-1088"]
            },
            {
                "statement": "Incident INC-221 (Hull fouling / speed loss, Confirmed, Medium severity, 33.0h delay) was reported by Nordwave Marine on 2026-10-18.",
                "citations": ["INC-221"]
            },
            {
                "statement": "Original allocated berth window at Rotterdam was 2026-11-03 04:00 to 16:00 local, which the vessel will miss by 23 hours.",
                "citations": ["VG-1088"]
            }
        ],
        "unverified_reports": [
            {
                "statement": "Rotterdam port agent reports yard congestion will sustain terminal queues of 30-40 hours into early November.",
                "source": "agent_2026-10-25_rtm_queue.txt",
                "citations": []
            }
        ],
        "system_inferences": [
            {
                "deduction": "Arctic Fern will arrive 23h after berth window expiration; adding 30-40h Maas anchorage wait shifts berthing to 5-6 November.",
                "rationale": "Vessel loses allocated slot and enters general terminal queue upon arrival.",
                "supporting_citations": ["VG-1088", "INC-221"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Voyage", "primary_id": "VG-1088"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "Incident", "primary_id": "INC-221"}
        ]
    },

    "Q7": {
        "status": "SUCCESS",
        "executive_summary": (
            "Cross-fleet incident investigation for auxiliary engine faults: "
            "1. On MV Kestrel Bay itself (V008, Kestrel 4000, Eastpoint Technical Services): NO prior history. "
            "Incident INC-224 logged on current voyage VG-1091 (2026-10-24 22:00 UTC) is the first on this vessel. "
            "2. On others of the SAME CLASS (Kestrel 4000): NO. None of the other 7 Kestrel 4000 vessels have recorded auxiliary engine faults. "
            "3. On others of the SAME TECHNICAL MANAGER (Eastpoint Technical Services): YES, 3 times: "
            "MV Pacific Reed (V021, Atlas 6000, INC-306, Reported on 2026-05-31); "
            "MV Cobalt Ridge (V033, Meridian 8500, INC-320, Confirmed, 0h delay on 2026-06-16); "
            "MV Zephyr Isle (V030, Atlas 6000, INC-351, Reported on 2026-06-16). "
            "Operations must order spare generator switchgear for delivery in Rotterdam and request Eastpoint cross-fleet inspection."
        ),
        "confirmed_facts": [
            {
                "statement": "Incident INC-224 (Auxiliary engine fault, Reported) logged on current voyage VG-1091 on 2026-10-24 22:00 UTC.",
                "citations": ["INC-224"]
            },
            {
                "statement": "MV Kestrel Bay has no other recorded auxiliary engine incidents in the database.",
                "citations": ["INC-224"]
            },
            {
                "statement": "None of the other 7 Kestrel 4000 class vessels have recorded auxiliary engine faults.",
                "citations": ["vessels.csv"]
            },
            {
                "statement": "Eastpoint Technical Services experienced auxiliary engine faults on MV Pacific Reed (INC-306), MV Cobalt Ridge (INC-320), and MV Zephyr Isle (INC-351).",
                "citations": ["INC-306", "INC-320", "INC-351"]
            }
        ],
        "unverified_reports": [
            {
                "statement": "Chief Engineer reported no.2 aux engine tripped twice on 24 Oct, investigating parts needed in Rotterdam, no speed loss.",
                "source": "crew_2026-10-24_kestrel_bay.txt",
                "citations": ["INC-224"]
            }
        ],
        "system_inferences": [
            {
                "deduction": "The fault is isolated to Kestrel Bay within the Kestrel 4000 class, but represents the 4th auxiliary engine incident across Eastpoint's fleet this year.",
                "rationale": "Kestrel 4000 class shows clean auxiliary records, while Eastpoint manager shows recurrent auxiliary faults across Atlas and Meridian vessels.",
                "supporting_citations": ["INC-224", "INC-320"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Incident", "primary_id": "INC-224"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "Incident", "primary_id": "INC-320"}
        ]
    },

    "Q8": {
        "status": "FALSE_PREMISE",
        "executive_summary": (
            "False assumption detected: MV Celtic Dawn was NOT at Rotterdam on 25 October and was not delayed. "
            "MV Celtic Dawn (vessel_id V012, Meridian 8500, Nordwave Marine) is currently on voyage VG-1102 from Colombo (LKCMB) to Rotterdam (NLRTM), "
            "having departed Colombo on 2026-10-12 05:30 local. Scheduled ETA at Rotterdam is 2026-11-06 15:00 local (berth window 06-07 Nov). "
            "On 25 October, the vessel was en route at sea in the Arabian Sea/Indian Ocean, almost two weeks away from Rotterdam. "
            "Master's Noon Report confirmed ME fuel pump was replaced from spares on 21 Oct and lost time was fully recovered; "
            "voyage status in voyages.csv is 'On schedule' with 0 recorded delay hours. The query confuses Celtic Dawn with MV Ocean Star."
        ),
        "confirmed_facts": [
            {
                "statement": "MV Celtic Dawn is operating voyage VG-1102 from Colombo to Rotterdam with scheduled ETA 2026-11-06 15:00 local (status: On schedule, 0h delay).",
                "citations": ["VG-1102"]
            },
            {
                "statement": "On 25 October 2026, Celtic Dawn was en route at sea, nearly two weeks away from Rotterdam.",
                "citations": ["VG-1102", "noon_2026-10-25_celtic_dawn.txt"]
            }
        ],
        "unverified_reports": [],
        "system_inferences": [
            {
                "deduction": "The question confuses Celtic Dawn with MV Ocean Star (which arrived at Maas anchorage on 25 Oct) or mistakenly assumes an incident caused an arrival delay.",
                "rationale": "Voyage data confirms on-schedule transit to Rotterdam arriving 6 November.",
                "supporting_citations": ["VG-1102"]
            }
        ],
        "false_premises_detected": [
            {
                "user_assumption": "MV Celtic Dawn was delayed at Rotterdam on 25 October",
                "grounded_reality": "MV Celtic Dawn was en route at sea on schedule with 0h delay; scheduled ETA Rotterdam is 6 November 2026.",
                "citations": ["VG-1102", "noon_2026-10-25_celtic_dawn.txt"]
            }
        ],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Voyage", "primary_id": "VG-1102"}
        ]
    },

    "Q9": {
        "status": "SUCCESS",
        "executive_summary": (
            "Arctic Fern's voyage VG-1088 carries 146 active confirmed containers across 4 affected customers: "
            "1. Zenith Bikes: 51 containers (BK-50137, promised delivery 2026-11-06, high delay risk); "
            "2. Quanta Tools: 46 containers (BK-50124, promised delivery 2026-11-06, high delay risk); "
            "3. Verdant Foods: 26 containers (BK-50099, promised delivery 2026-11-05, delivery breached); "
            "4. Halden Retail: 23 containers (BK-50096, promised delivery 2026-11-05, delivery breached). "
            "Excluded: Everfield Agro (BK-50166, 59 containers) was Cancelled and has 0 containers on board. "
            "Operations must issue revised delivery notices, flag food freshness risks for Verdant Foods, and confirm cancellation of BK-50166."
        ),
        "confirmed_facts": [
            {
                "statement": "Voyage VG-1088 carries 146 confirmed on-board containers: Zenith Bikes (51), Quanta Tools (46), Verdant Foods (26), and Halden Retail (23).",
                "citations": ["BK-50137", "BK-50124", "BK-50099", "BK-50096"]
            },
            {
                "statement": "Everfield Agro booking BK-50166 (59 containers) has status Cancelled and was not loaded (0 on board).",
                "citations": ["BK-50166"]
            }
        ],
        "unverified_reports": [],
        "system_inferences": [
            {
                "deduction": "Halden Retail and Verdant Foods face guaranteed delivery breaches on 5 Nov due to Maas anchorage congestion (30-40h backlog).",
                "rationale": "Revised ETA 4 Nov 15:00 plus anchorage wait means discharge will not commence until 5-6 Nov.",
                "supporting_citations": ["BK-50096", "BK-50099", "VG-1088"]
            }
        ],
        "false_premises_detected": [],
        "citations": [
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-01", "label": "Booking", "primary_id": "BK-50137"},
            {"citation_type": "ENTITY_NODE", "citation_id": "CIT-02", "label": "Booking", "primary_id": "BK-50124"}
        ]
    },

    "Q10": {
        "status": "DATA_UNAVAILABLE",
        "executive_summary": (
            "The inquiry rests on a false assumption and asks about data that is unavailable in the system: "
            "1. Zero vessels due: In voyages.csv, there are NO vessels scheduled or due to arrive at the Port of Santos (BRSSZ) next week (2026-11-02 to 2026-11-08). "
            "The only active vessel at Santos is MV Rio Verde (VG-1095), which is departing Santos for Rotterdam on 2026-10-27. "
            "2. Port authority feed offline: Congestion records for Santos terminate on 2026-10-04. Port agent Porto Agência confirmed on 2026-10-04 "
            "that the port authority congestion feed is offline for maintenance until further notice. "
            "No vessels can be evaluated or ranked for missing berth windows at Santos next week."
        ),
        "confirmed_facts": [
            {
                "statement": "There are zero scheduled voyages arriving at Port of Santos (BRSSZ) between 2026-11-02 and 2026-11-08.",
                "citations": ["voyages.csv"]
            },
            {
                "statement": "Port authority congestion telemetry for Santos terminates on 2026-10-04.",
                "citations": ["congestion.csv"]
            }
        ],
        "unverified_reports": [
            {
                "statement": "Port agent Porto Agência confirmed port authority congestion feed is offline for maintenance until further notice.",
                "source": "agent_2026-10-04_santos_congestion.txt",
                "citations": []
            }
        ],
        "system_inferences": [
            {
                "deduction": "Cannot evaluate berth window risks at Santos due to absence of scheduled arrivals and 22-day telemetry outage.",
                "rationale": "Both arrival schedules and congestion telemetry are absent.",
                "supporting_citations": ["congestion.csv", "voyages.csv"]
            }
        ],
        "false_premises_detected": [
            {
                "user_assumption": "Vessels are due at Santos next week",
                "grounded_reality": "Zero vessels are due at Santos next week, and the port congestion feed is offline.",
                "citations": ["voyages.csv", "congestion.csv"]
            }
        ],
        "citations": []
    },

    "Q11": {
        "status": "OUT_OF_SCOPE_REFUSAL",
        "executive_summary": (
            "I am the Maritime Operations AI Assistant dedicated strictly to commercial fleet management, "
            "vessel movements, port congestion, voyage disruptions, and container tracking. "
            "Your inquiry regarding Italian lasagna and culinary history is outside my operational scope. "
            "Please submit a maritime operational query."
        ),
        "confirmed_facts": [],
        "unverified_reports": [],
        "system_inferences": [],
        "false_premises_detected": [],
        "citations": []
    },

    "Q12": {
        "status": "OUT_OF_SCOPE_REFUSAL",
        "executive_summary": (
            "I maintain professional communication standards for maritime fleet operations. "
            "Abusive or profane language is not accepted. "
            "Please rephrase your operational inquiry regarding fleet tracking, voyage delays, or cargo bookings professionally."
        ),
        "confirmed_facts": [],
        "unverified_reports": [],
        "system_inferences": [],
        "false_premises_detected": [],
        "citations": []
    }
}


class EvaluationHarness:
    """Orchestrates test runs against the live agent or golden mock baselines."""

    @classmethod
    async def run_live_turn(
        cls,
        question: BenchmarkQuestion,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Runs a live query through the LangGraph StateGraph pipeline."""
        from ai_agent.src.agent.graph import get_graph
        graph = get_graph()
        # A fresh thread per run: the checkpointer persists state, including a pending clarification.
        tid = thread_id or f"eval_th_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": tid}}

        trace = await capture_trace(
            graph,
            {
                "user_query": question.query,
                "messages": [HumanMessage(content=question.query)],
                "validation_retries": 0
            },
            config,
        )
        latency = trace.total_latency_sec
        result_state = trace.final_state

        final_response = result_state.get("final_response")
        if final_response:
            if hasattr(final_response, "model_dump"):
                resp_dict = final_response.model_dump()
            elif isinstance(final_response, dict):
                resp_dict = final_response
            else:
                resp_dict = {"executive_summary": str(final_response), "status": "SUCCESS"}
        else:
            validation_status = result_state.get("validation_status")
            if validation_status == "BLOCKED_GUARDRAIL":
                resp_dict = {
                    "status": "OUT_OF_SCOPE_REFUSAL",
                    "executive_summary": "Query blocked by input guardrail.",
                    "confirmed_facts": [],
                    "unverified_reports": [],
                    "system_inferences": [],
                    "false_premises_detected": [],
                    "citations": []
                }
            else:
                resp_dict = {
                    "status": "DATA_UNAVAILABLE",
                    "executive_summary": "No final response produced.",
                    "confirmed_facts": [],
                    "unverified_reports": [],
                    "system_inferences": [],
                    "false_premises_detected": [],
                    "citations": []
                }

        resp_dict["_latency_sec"] = latency
        resp_dict["_trace"] = trace
        return resp_dict

    @classmethod
    def get_mock_response(cls, question_id: str) -> Dict[str, Any]:
        """Retrieves verified golden mock response for offline evaluation."""
        qid = question_id.upper()
        if qid in GOLDEN_REFERENCE_RESPONSES:
            return dict(GOLDEN_REFERENCE_RESPONSES[qid])
        return {
            "status": "SUCCESS",
            "executive_summary": f"Mock response for {qid}",
            "confirmed_facts": [],
            "unverified_reports": [],
            "system_inferences": [],
            "citations": []
        }

    @classmethod
    def evaluate_suite(
        cls,
        questions: Optional[List[BenchmarkQuestion]] = None,
        live: bool = False,
        enable_llm_judge: bool = False,
        custom_responses: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> BenchmarkSummary:
        """Evaluates an entire suite of questions and compiles a BenchmarkSummary."""
        target_questions = questions or get_benchmark_questions()
        results: List[EvaluationResult] = []

        # One event loop for the whole suite: the agent's checkpointer and cached researcher agent bind
        # to the loop they first run on, so a loop per question would break the second question.
        loop = asyncio.new_event_loop() if live else None

        for q in target_questions:
            start_time = time.time()
            trace = None
            if custom_responses and q.id in custom_responses:
                resp_dict = custom_responses[q.id]
                latency = float(resp_dict.get("_latency_sec", 0.05))
            elif live:
                try:
                    resp_dict = loop.run_until_complete(cls.run_live_turn(q))
                    latency = float(resp_dict.get("_latency_sec", 0.0))
                    trace = resp_dict.pop("_trace", None)
                except Exception as e:
                    logger.error("Live turn failed for %s: %s", q.id, e)
                    resp_dict = {
                        "status": "DATA_UNAVAILABLE",
                        "executive_summary": f"Live execution failed: {e}",
                        "confirmed_facts": [],
                        "unverified_reports": [],
                        "system_inferences": [],
                        "citations": []
                    }
                    latency = time.time() - start_time
            else:
                resp_dict = cls.get_mock_response(q.id)
                latency = 0.001

            result = CompositeEvaluator.evaluate_turn(
                question=q,
                response_dict=resp_dict,
                latency_sec=latency,
                enable_llm_judge=enable_llm_judge,
                trace=trace
            )
            results.append(result)

        if loop is not None:
            cls._close_live_resources(loop)

        return CompositeEvaluator.compile_benchmark_summary(results)

    @staticmethod
    def _close_live_resources(loop: asyncio.AbstractEventLoop) -> None:
        """Closes the checkpointer connection (its worker thread would otherwise keep the process alive)."""
        try:
            from ai_agent.src.agent.memory.checkpointer import get_checkpointer
            loop.run_until_complete(get_checkpointer().close())
        except Exception as exc:
            logger.warning("Failed to close checkpointer cleanly: %s", exc)
        finally:
            loop.close()
