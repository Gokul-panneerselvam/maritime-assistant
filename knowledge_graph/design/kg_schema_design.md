# Maritime Domain Knowledge Graph Schema Specification

## 1. Schema Overview

The Maritime Operations Knowledge Graph integrates structured operational tabular data (fleet master data, voyages, port calls, congestion, incidents, cargo bookings) with unstructured operational communications (noon reports, port agent logs, technical bulletins, customer inquiries).

All timestamps and date fields are standardized to **UTC** (ISO 8601: `YYYY-MM-DDTHH:MM:SSZ` or Date: `YYYY-MM-DD`). Local port timestamps from tabular sources are converted to UTC using the IANA timezone of the respective port.

---

## 2. Graph Node Definitions & Attributes

The schema comprises **13 node labels** (12 core labels plus `Organization`, added so every message sender is a real node):

### 1. `Vessel`
Represents an individual physical vessel in the fleet.
* **Source Table**: `vessels.csv`
* **Primary Identifier**: `vessel_id` (e.g., `"V001"`)
* **Attributes**:
  * `vessel_id` (STRING, Unique PK): Internal vessel identifier.
  * `name` (STRING): Vessel name (e.g., `"MV Ocean Star"`).
  * `imo` (INTEGER, Unique): International Maritime Organization 7-digit identifier (e.g., `9876543`).
* **Graph Outgoing Edges**:
  * `[:OF_TYPE]->(:VesselType)`
  * `[:OF_CLASS]->(:VesselClass)`
  * `[:MANAGED_BY]->(:TechnicalManager)`
  * `[:OPERATES_VOYAGE]->(:Voyage)`

---

### 2. `VesselType`
Represents the functional classification or vessel category.
* **Source Table**: Extracted from `vessels.csv` (`type` column).
* **Primary Identifier**: `type_id` / `name` (e.g., `"Container ship"`, `"Feeder"`, `"Bulk carrier"`)
* **Attributes**:
  * `type_id` (STRING, Unique PK): Normalized type identifier (e.g., `"CONTAINER_SHIP"`, `"FEEDER"`, `"BULK_CARRIER"`).
  * `name` (STRING): Display name (e.g., `"Container ship"`).
  * `description` (STRING, Optional): Descriptive summary of vessel operational category.

---

### 3. `VesselClass`
Represents the structural hull design, series, and equipment architecture. Critical for analyzing sister-ship fleet patterns and recurring mechanical faults (e.g., cooling pump failures across *Meridian 8500* vessels).
* **Source Table**: Extracted from `vessels.csv` (`vessel_class` column).
* **Primary Identifier**: `class_id` / `name` (e.g., `"Meridian 8500"`, `"Atlas 6000"`, `"Kestrel 4000"`, `"Coastal 1700"`, `"Titan Bulk 82"`)
* **Attributes**:
  * `class_id` (STRING, Unique PK): Unique class identifier.
  * `name` (STRING): Class designation name.
  * `nominal_capacity_teu` (INTEGER, Optional): Standard container capacity (TEU) or deadweight tonnage.

---

### 4. `TechnicalManager`
Represents the third-party ship management company responsible for technical fleet superintendency, maintenance schedules, bulletins, and engineering operations.
* **Source Table**: Extracted from `vessels.csv` (`technical_manager` column).
* **Primary Identifier**: `manager_id` / `name` (e.g., `"Harbourline Ship Management"`, `"Nordwave Marine"`, `"Eastpoint Technical Services"`, `"Sulamar Gestão Naval"`, `"Bluefin Fleet Services"`)
* **Attributes**:
  * `manager_id` (STRING, Unique PK): Normalized slug/identifier.
  * `name` (STRING): Full corporate entity name.
  * `contact_email` (STRING, Optional): Management operations email domain or contact.

---

### 5. `Port`
Represents a seaport terminal hub with defined maritime boundaries, anchorages, and local operational timezones.
* **Source Table**: `ports.csv`
* **Primary Identifier**: `port_code` (e.g., `"SGSIN"`, `"NLRTM"`, `"DEHAM"`)
* **Attributes**:
  * `port_code` (STRING, Unique PK): UN/LOCODE 5-letter code (e.g., `"NLRTM"`).
  * `name` (STRING): Formal port name (e.g., `"Port of Rotterdam"`).
  * `country` (STRING): Country name (e.g., `"Netherlands"`).
  * `timezone` (STRING): IANA timezone identifier (e.g., `"Europe/Amsterdam"`, `"Asia/Singapore"`).
* **Graph Outgoing Edges**:
  * `[:HAS_CONGESTION]->(:Congestion)`

---

### 6. `Voyage`
Represents an individual commercial voyage transit executed by a vessel between an origin port and a destination port.
* **Source Table**: `voyages.csv`
* **Primary Identifier**: `voyage_id` (e.g., `"VG-1042"`)
* **Attributes** (Both UTC and local time fields retained):
  * `voyage_id` (STRING, Unique PK): Voyage code.
  * `departure_utc` (DATETIME): Departure timestamp in UTC (converted from `departure_local` using origin port timezone).
  * `departure_local` (STRING / DATETIME): Original departure in origin port local time.
  * `original_eta_utc` (DATETIME): Contractual ETA in UTC (converted from `original_eta_local` using destination port timezone).
  * `original_eta_local` (STRING / DATETIME): Contractual ETA in destination port local time.
  * `revised_eta_utc` (DATETIME): Revised ETA in UTC (converted from `revised_eta_local` using destination port timezone).
  * `revised_eta_local` (STRING / DATETIME): Revised ETA in destination port local time.
  * `berth_window_start_utc` (DATETIME): Berth window opening in UTC (converted using destination port timezone).
  * `berth_window_start_local` (STRING / DATETIME): Berth window opening in destination port local time.
  * `berth_window_end_utc` (DATETIME): Berth window closing in UTC (converted using destination port timezone).
  * `berth_window_end_local` (STRING / DATETIME): Berth window closing in destination port local time.
  * `status` (STRING): Lifecycle status (`"Completed"`, `"Delayed"`, `"Scheduled"`, `"On schedule"`).
  * `recorded_delay_hours` (FLOAT): Operations-recorded delay hours (`revised_eta - original_eta`).
* **Graph Outgoing Edges**:
  * `[:OPERATED_BY]->(:Vessel)` (or inverse `(:Vessel)-[:OPERATES_VOYAGE]->(:Voyage)`)
  * `[:DEPARTS_FROM]->(:Port)` (Origin port)
  * `[:ARRIVES_AT]->(:Port)` (Destination port)
  * `[:HAS_PORT_CALL]->(:PortCall)`
  * `[:EXPERIENCED_INCIDENT]->(:Incident)`

---

### 7. `PortCall`
Represents physical terminal and anchorage milestones recorded during a vessel's stop at a port.
* **Source Table**: `port_calls.csv`
* **Primary Identifier**: `call_id` (e.g., `"PC-7001"`)
* **Attributes** (Native UTC in dataset):
  * `call_id` (STRING, Unique PK): Port call event identifier.
  * `call_type` (STRING): Event type (`"Departure"` or `"Arrival"`).
  * `anchorage_arrival_utc` (DATETIME, Nullable): Timestamp vessel entered port outer anchorage.
  * `berth_scheduled_utc` (DATETIME, Nullable): Assigned terminal berthing slot.
  * `berthing_utc` (DATETIME, Nullable): Actual timestamp vessel made fast alongside berth.
  * `departure_utc` (DATETIME, Nullable): Timestamp vessel unmoored and departed berth.
  * `anchorage_wait_hours` (FLOAT, Computed): Duration spent waiting at anchor (`berthing_utc - anchorage_arrival_utc`).
  * `port_stay_hours` (FLOAT, Computed): Total port turnaround duration (`departure_utc - berthing_utc`).
* **Graph Outgoing Edges**:
  * `[:AT_PORT]->(:Port)`
  * `[:PART_OF_VOYAGE]->(:Voyage)`
  * `[:CALL_BY]->(:Vessel)`

---

### 8. `Incident`
Represents an unexpected operational disruption, mechanical defect, weather diversion, regulatory delay, or labor stoppage.
* **Source Table**: `incidents.csv`
* **Primary Identifier**: `incident_id` (e.g., `"INC-201"`)
* **Attributes**:
  * `incident_id` (STRING, Unique PK): Incident identifier.
  * `type` (STRING): Incident category (`"Engine cooling fault"`, `"Adverse weather / rerouting"`, `"Customs documentation query"`, `"Bunkering delay"`, `"Hull fouling / speed loss"`, etc.).
  * `status` (STRING): Investigation status (`"Confirmed"`, `"Reported"`, `"Under review"`, `"Dismissed"`).
  * `severity` (STRING): Impact classification (`"Low"`, `"Medium"`, `"High"`, `"Unknown"`).
  * `reported_utc` (DATETIME): Incident logged timestamp in UTC.
  * `source` (STRING): Reporting channel (`"Master's report"`, `"Crew message"`, `"Agent email"`, `"Technical manager"`, `"Port agent"`).
  * `attributed_delay_hours` (FLOAT, Nullable): Official delay duration allocated to this specific root cause.
* **Graph Outgoing Edges**:
  * `[:OCCURRED_ON_VOYAGE]->(:Voyage)`
  * `[:AFFECTS_VESSEL]->(:Vessel)` (Derived shortcut)

---

### 9. `Congestion`
Represents daily port-wide water-side and terminal bottleneck indicators.
* **Source Table**: `congestion.csv`
* **Primary Identifier**: `congestion_id` (Composite key: `CONG_<port>_<date>`, e.g., `"CONG_SGSIN_2026-09-17"`)
* **Attributes**:
  * `congestion_id` (STRING, Unique PK): Composite key.
  * `date_utc` (DATE / STRING): Observation date in UTC (`"YYYY-MM-DD"`).
  * `congestion_level` (STRING): Category (`"Low"`, `"Moderate"`, `"High"`).
  * `avg_wait_hours` (FLOAT): Port-wide average anchorage waiting time before berthing.
  * `vessels_at_anchor` (INTEGER): Number of ships queued at outer anchorage.
  * `source` (STRING): Feed source (`"Port authority feed"`).
* **Graph Outgoing Edges**:
  * `[:RECORDED_AT]->(:Port)` (or inverse `(:Port)-[:HAS_CONGESTION]->(:Congestion)`)

---

### 10. `Booking`
Represents a customer commercial freight allocation booked aboard a voyage.
* **Source Table**: `bookings.csv`
* **Primary Identifier**: `booking_id` (e.g., `"BK-50001"`)
* **Attributes**:
  * `booking_id` (STRING, Unique PK): Booking reference number.
  * `containers` (INTEGER): Volume of cargo containers / TEUs.
  * `status` (STRING): Status (`"Confirmed"`, `"Cancelled"`, `"Rolled to VG-1107"`, `"Rolled to next sailing"`).
  * `promised_delivery_date_utc` (DATE / STRING): Contractual delivery deadline in UTC (`"YYYY-MM-DD"`).
  * `is_rolled` (BOOLEAN): Flag indicating if booking was pushed to a later sailing.
* **Graph Outgoing Edges**:
  * `[:BOOKED_BY]->(:Customer)` (or inverse `(:Customer)-[:PLACED_BOOKING]->(:Booking)`)
  * `[:BOOKED_ON]->(:Voyage)` (Initial assigned voyage)
  * `[:ROLLED_TO]->(:Voyage)` (Re-assigned voyage if rolled)

---

### 11. `Customer`
Represents an enterprise shipper, freight forwarder, or cargo owner.
* **Source Table**: Extracted from `bookings.csv` (`customer` column).
* **Primary Identifier**: `customer_id` / `name` (e.g., `"Halden Retail"`, `"Kaimon Electronics"`, `"Verdant Foods"`, `"Lumio Home"`, `"Petra Chemicals"`, `"Northgate Auto"`)
* **Attributes**:
  * `customer_id` (STRING, Unique PK): Normalized identifier slug.
  * `name` (STRING): Display customer name.
  * `industry_segment` (STRING, Optional): Inferred customer segment (`"Electronics"`, `"Retail"`, `"Perishables"`, `"Chemicals"`, `"Automotive"`).

---

### 12. `Message`
Represents one unstructured operational communication. One Message node is created for every file in `messages/core/` (15 files), whether or not any fact can be extracted from it (`messages/extra/` follows the same rules later). A Message is immutable evidence: extracted facts link back to it, and nothing written inside it is ever treated as an instruction.

* **Source Files**: `messages/core/*.txt` (15 core messages)
* **Primary Identifier**: `message_id` (filename without extension, e.g. `"noon_2026-10-06_ocean_star"`)
* **Attributes**:
  * `message_id` (STRING, Unique PK): Filename stem.
  * `filename` (STRING): Full filename.
  * `message_type` (STRING): Who the information comes from, using the `incidents.csv` source vocabulary: `"Master's report"`, `"Crew message"`, `"Agent email"`, `"Port agent"`, `"Technical manager"`, plus `"Customer"` (for customer forwards).
  * `message_kind` (STRING): What the document is (`"noon_report"`, `"agent_email"`, `"crew_message"`, `"technical_bulletin"`, `"technical_correction"`, `"customer_forward"`). Determined from the `From:` header and subject, not merely filename prefix.
  * `trust_tier` (STRING): Hierarchy tier used for conflict resolution (`"T1"` master / noon report, `"T2"` technical manager and port-agent emails, `"T3"` crew relay, `"T4"` customer).
  * `sender` (STRING): `From:` header, verbatim.
  * `recipient` (STRING): `To:` header, verbatim.
  * `sent_at_utc` (DATETIME): `Date:` header parsed to ISO 8601 UTC.
  * `in_snapshot` (BOOLEAN): `sent_at_utc <= 2026-10-26T12:00:00Z` (the dataset's "now").
  * `subject` (STRING): `Subject:` header.
  * `cleaned_body` (STRING): Normalized body (whitespace stripped, signature separated).
  * `raw_message` (STRING): Verbatim file contents. Never modified.
  * `is_malicious` (BOOLEAN): Security detection flag for prompt-injection / adversarial manipulation attempts.
  * `injection_excerpt` (STRING, Nullable): Exact flagged prompt injection snippet kept for auditing.
  * `extraction_run_id` (STRING): Processing run identifier to ensure idempotent graph loading.
* **Graph Outgoing Edges**: See Section 3.1, Message Edge Matrix.

---

### 13. `Organization`
A sender that is not already a node: the six port-agent companies in the core messages. Technical managers and customers remain represented under `TechnicalManager` and `Customer`.

* **Source**: `From:` header and signature of agent emails.
* **Primary Identifier**: `org_id` (slug, e.g. `"van-dijk-shipping-agency"`)
* **Attributes**:
  * `org_id` (STRING, Unique PK): Unique organization slug.
  * `name` (STRING): Display name (e.g. `"Van Dijk Shipping Agency"`, `"Lion City Agencies"`, `"Scheldt Maritime Agency"`, `"Harwich Port Services"`, `"Elbe Port Agency"`, `"Gulf Marine Agency"`).
  * `org_type` (STRING): Classification (`"port_agent"`).
* **Graph Outgoing Edges**:
  * `[:BASED_AT]->(:Port)` (Agent's home port: Van Dijk to NLRTM, Lion City to SGSIN, Scheldt to BEANR, Harwich to GBFXT, Elbe to DEHAM, Gulf Marine to AEJEA).

---

## 3. Knowledge Graph Edge (Relationship) Matrix

| Edge Relationship | Source Node | Target Node | Cardinality | Semantic Description & Source |
| :--- | :--- | :--- | :---: | :--- |
| `[:OF_TYPE]` | `Vessel` | `VesselType` | N : 1 | Categorizes vessel (from `vessels.csv.type`). |
| `[:OF_CLASS]` | `Vessel` | `VesselClass` | N : 1 | Specifies hull / design class (from `vessels.csv.vessel_class`). |
| `[:MANAGED_BY]` | `Vessel` | `TechnicalManager` | N : 1 | Specifies technical superintendent (from `vessels.csv.technical_manager`). |
| `[:OPERATES_VOYAGE]` | `Vessel` | `Voyage` | 1 : N | Vessel assigned to execute the voyage (from `voyages.csv.vessel_id`). |
| `[:DEPARTS_FROM]` | `Voyage` | `Port` | N : 1 | Origin port of the voyage (from `voyages.csv.origin`). |
| `[:ARRIVES_AT]` | `Voyage` | `Port` | N : 1 | Scheduled destination port (from `voyages.csv.destination`). |
| `[:HAS_PORT_CALL]` | `Voyage` | `PortCall` | 1 : N | Milestone stops during the voyage (from `port_calls.csv.voyage_id`). |
| `[:AT_PORT]` | `PortCall` | `Port` | N : 1 | Port facility where call occurs (from `port_calls.csv.port`). |
| `[:CALL_BY]` | `PortCall` | `Vessel` | N : 1 | Vessel executing the call (from `port_calls.csv.vessel_id`). |
| `[:HAS_CONGESTION]` | `Port` | `Congestion` | 1 : N | Daily congestion status logs for a port (from `congestion.csv.port`). |
| `[:EXPERIENCED_INCIDENT]` | `Voyage` | `Incident` | 1 : N | Incidents recorded on this voyage (from `incidents.csv.voyage_id`). |
| `[:AFFECTS_VESSEL]` | `Incident` | `Vessel` | N : 1 | Vessel impacted by the disruption (derived via Voyage). |
| `[:PLACED_BOOKING]` | `Customer` | `Booking` | 1 : N | Shipper who booked cargo space (from `bookings.csv.customer`). |
| `[:BOOKED_ON]` | `Booking` | `Voyage` | N : 1 | Voyage scheduled to carry containers (from `bookings.csv.voyage_id`). |
| `[:ROLLED_TO]` | `Booking` | `Voyage` | N : 1 | Subsequent voyage if cargo was rolled (from `bookings.csv.status`). |
| `[:BASED_AT]` | `Organization` | `Port` | N : 1 | Home port of a port agent (from agent name and signature). |

---

### 3.1 Message Edge Matrix

#### Operational Linking Rules
1. **Exactly one sender edge per message**: `[:SENT_BY_VESSEL]`, `[:SENT_BY_ORG]`, `[:ISSUED_BY_MANAGER]`, or `[:SENT_BY_CUSTOMER]`. Derived from the `From:` header, not the filename.
2. **`ABOUT_*` vs `REFERENCES_*`**: Use `ABOUT_*` when the message makes definitive operational statements about the entity (e.g. status, performance, delays). Use `REFERENCES_*` when it only names or cites it in passing (e.g. a line-up message naming future calls).
3. **Incident Edges (choose one per incident)**:
   * `[:REPORTS_INCIDENT]`: Message is the initial source of the incident.
   * `[:CORROBORATES_INCIDENT]`: Confirms or adds detail without overriding values.
   * `[:REVISES_INCIDENT]`: Changes an operational value (delay hours, status, severity) and supersedes an earlier statement.
   * `[:CORRECTS_INCIDENT]`: Fixes an erroneous description in an earlier report (component, subsystem, root cause).
4. **No Forced Linking**: If an entity is ambiguous or cannot be uniquely verified, leave it unlinked.

#### Edge Properties on Message Edges
To keep the graph lightweight and clean, message edges carry **only temporal metadata**:

| Property | Type | Description |
| :--- | :--- | :--- |
| `event_time_utc` | DATETIME (Nullable) | Timestamp when the described event occurred, if stated (differs from message `sent_at_utc`). |
| `temporal` | STRING | Operational temporal orientation: `"past"`, `"current"`, or `"planned"`. |

#### Message Relationships Specification

| Edge | Source Node | Target Node | Cardinality | Semantic Description | Edge Properties |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `[:SENT_BY_VESSEL]` | `Message` | `Vessel` | N : 1 | Transmitted by the ship's Master or crew | `temporal`, `event_time_utc` |
| `[:SENT_BY_ORG]` | `Message` | `Organization` | N : 1 | Sent by a local port agency | `temporal`, `event_time_utc` |
| `[:ISSUED_BY_MANAGER]` | `Message` | `TechnicalManager` | N : 1 | Bulletin or correction issued by technical ship manager | `temporal`, `event_time_utc` |
| `[:SENT_BY_CUSTOMER]` | `Message` | `Customer` | N : 1 | Inbound communication from customer/shipper | `temporal`, `event_time_utc` |
| `[:ABOUT_VESSEL]` | `Message` | `Vessel` | N : N | Message makes operational statements about vessel | `temporal`, `event_time_utc` |
| `[:ABOUT_VOYAGE]` | `Message` | `Voyage` | N : N | Message reports on voyage progress, delays, or revised ETA | `temporal`, `event_time_utc` |
| `[:ABOUT_PORT_CALL]` | `Message` | `PortCall` | N : N | Reports on anchorage arrival, berthing, or port stay | `temporal`, `event_time_utc` |
| `[:ABOUT_CLASS]` | `Message` | `VesselClass` | N : N | Fleet bulletin or finding regarding a vessel class | `temporal`, `event_time_utc` |
| `[:EVENT_AT_PORT]` | `Message` | `Port` | N : N | Port location where the reported event occurred | `temporal`, `event_time_utc` |
| `[:DESCRIBES_CONGESTION]` | `Message` | `Congestion` | N : N | Advisory on waiting times, anchorage queues, or feed outage | `temporal`, `event_time_utc` |
| `[:REPORTS_INCIDENT]` | `Message` | `Incident` | N : N | Original source reporting an incident | `temporal`, `event_time_utc` |
| `[:CORROBORATES_INCIDENT]`| `Message` | `Incident` | N : N | Authoritatively corroborates an existing incident | `temporal`, `event_time_utc` |
| `[:REVISES_INCIDENT]` | `Message` | `Incident` | N : N | Revises incident status, duration, or delay hours | `temporal`, `event_time_utc` |
| `[:CORRECTS_INCIDENT]` | `Message` | `Incident` | N : N | Corrects root-cause component or misattribution | `temporal`, `event_time_utc` |
| `[:REFERENCES_VESSEL]` | `Message` | `Vessel` | N : N | Mentions vessel by name or IMO | `temporal`, `event_time_utc` |
| `[:REFERENCES_VESSEL_TYPE]`| `Message` | `VesselType` | N : N | Mentions a vessel type | `temporal`, `event_time_utc` |
| `[:REFERENCES_CLASS]` | `Message` | `VesselClass` | N : N | Mentions a vessel class | `temporal`, `event_time_utc` |
| `[:REFERENCES_MANAGER]` | `Message` | `TechnicalManager` | N : N | Mentions a technical manager | `temporal`, `event_time_utc` |
| `[:REFERENCES_PORT]` | `Message` | `Port` | N : N | Mentions a port name or UN/LOCODE | `temporal`, `event_time_utc` |
| `[:REFERENCES_VOYAGE]` | `Message` | `Voyage` | N : N | Mentions a voyage number or ID | `temporal`, `event_time_utc` |
| `[:REFERENCES_BOOKING]` | `Message` | `Booking` | N : N | Mentions a booking or bill-of-lading reference | `temporal`, `event_time_utc` |
| `[:REFERENCES_CUSTOMER]`| `Message` | `Customer` | N : N | Mentions a customer/shipper name | `temporal`, `event_time_utc` |
| `[:CORRECTS_MESSAGE]` | `Message` | `Message` | N : 1 | Corrects an earlier message in the corpus | `temporal`, `event_time_utc` |
| `[:REFERENCES_MESSAGE]` | `Message` | `Message` | N : N | Cites another message or bulletin (e.g. cites TB-26-14) | `temporal`, `event_time_utc` |

#### Node-to-Message Edge Coverage Summary

| Node Label | Connected Message Relationships |
| :--- | :--- |
| `Vessel` | `SENT_BY_VESSEL`, `ABOUT_VESSEL`, `REFERENCES_VESSEL` |
| `VesselType` | `REFERENCES_VESSEL_TYPE` |
| `VesselClass` | `ABOUT_CLASS`, `REFERENCES_CLASS` |
| `TechnicalManager` | `ISSUED_BY_MANAGER`, `REFERENCES_MANAGER` |
| `Port` | `EVENT_AT_PORT`, `REFERENCES_PORT` *(Port agent base is reached via `(:Organization)-[:BASED_AT]->(:Port)`)* |
| `Voyage` | `ABOUT_VOYAGE`, `REFERENCES_VOYAGE` |
| `PortCall` | `ABOUT_PORT_CALL` |
| `Incident` | `REPORTS_INCIDENT`, `CORROBORATES_INCIDENT`, `REVISES_INCIDENT`, `CORRECTS_INCIDENT` |
| `Congestion` | `DESCRIBES_CONGESTION` |
| `Booking` | `REFERENCES_BOOKING` |
| `Customer` | `SENT_BY_CUSTOMER`, `REFERENCES_CUSTOMER` |
| `Organization` | `SENT_BY_ORG` |
| `Message` | `CORRECTS_MESSAGE`, `REFERENCES_MESSAGE` |

---

## 4. UTC Timezone Normalization Rules

In accordance with the DB requirement **"We gonna keep the UTC timezone in the DB"**:

1. **Origin Timestamps (`departure_local`)**:
   * Lookup `timezone` from `ports.csv` for the voyage's `origin` port code (e.g., `SGSIN` -> `"Asia/Singapore"`).
   * Localize the timestamp string to origin timezone and convert to UTC:
     $$\text{departure\_utc} = \text{astimezone}(\text{localize}(\text{departure\_local}, \text{TZ}_{\text{origin}}), \text{UTC})$$

2. **Destination Timestamps (`original_eta_local`, `revised_eta_local`, `berth_window_start_local`, `berth_window_end_local`)**:
   * Lookup `timezone` from `ports.csv` for the voyage's `destination` port code (e.g., `NLRTM` -> `"Europe/Amsterdam"`).
   * Localize each timestamp string to destination timezone and convert to UTC:
     $$\text{eta\_utc} = \text{astimezone}(\text{localize}(\text{eta\_local}, \text{TZ}_{\text{destination}}), \text{UTC})$$

3. **Port Calls & Incidents (`_utc`)**:
   * Already recorded with `Z` suffix (UTC ISO 8601). Ingested directly into `DATETIME` properties.

4. **Congestion & Bookings Dates**:
   * Standardized to ISO Date strings (`YYYY-MM-DD`) or UTC midnight datetime (`YYYY-MM-DDT00:00:00Z`).

5. **Operational Messages**:
   * Header `Date:` lines (e.g., `2026-10-06 06:00 UTC`) are parsed and converted to ISO 8601 UTC datetimes.

---

## 5. Schema Graph Visualization (Mermaid)

```mermaid
graph TD
    %% Node Definitions
    Vessel["<b>Vessel</b><br/>• vessel_id (PK)<br/>• name<br/>• imo"]
    VType["<b>VesselType</b><br/>• type_id (PK)<br/>• name"]
    VClass["<b>VesselClass</b><br/>• class_id (PK)<br/>• name"]
    TManager["<b>TechnicalManager</b><br/>• manager_id (PK)<br/>• name"]
    
    Port["<b>Port</b><br/>• port_code (PK)<br/>• name<br/>• country<br/>• timezone"]
    Voyage["<b>Voyage</b><br/>• voyage_id (PK)<br/>• departure_local & departure_utc<br/>• original_eta_local & original_eta_utc<br/>• revised_eta_local & revised_eta_utc<br/>• recorded_delay_hours<br/>• status"]
    PCall["<b>PortCall</b><br/>• call_id (PK)<br/>• call_type<br/>• anchorage_arrival_utc<br/>• berthing_utc<br/>• departure_utc"]
    
    Inc["<b>Incident</b><br/>• incident_id (PK)<br/>• type<br/>• severity<br/>• status<br/>• reported_utc<br/>• attributed_delay_hours"]
    Cong["<b>Congestion</b><br/>• congestion_id (PK)<br/>• date_utc<br/>• congestion_level<br/>• avg_wait_hours<br/>• vessels_at_anchor"]
    
    Cust["<b>Customer</b><br/>• customer_id (PK)<br/>• name"]
    Book["<b>Booking</b><br/>• booking_id (PK)<br/>• containers<br/>• status<br/>• promised_delivery_date_utc"]
    
    Msg["<b>Message (Core)</b><br/>• message_id (PK)<br/>• filename<br/>• message_type<br/>• message_kind<br/>• trust_tier<br/>• sender<br/>• recipient<br/>• sent_at_utc<br/>• subject<br/>• is_malicious"]
    Org["<b>Organization</b><br/>• org_id (PK)<br/>• name<br/>• org_type"]

    %% Core Relationships
    Vessel -->|OF_TYPE| VType
    Vessel -->|OF_CLASS| VClass
    Vessel -->|MANAGED_BY| TManager
    Vessel -->|OPERATES_VOYAGE| Voyage

    Voyage -->|DEPARTS_FROM| Port
    Voyage -->|ARRIVES_AT| Port
    Voyage -->|HAS_PORT_CALL| PCall
    Voyage -->|EXPERIENCED_INCIDENT| Inc

    PCall -->|AT_PORT| Port
    PCall -->|CALL_BY| Vessel

    Port -->|HAS_CONGESTION| Cong

    Cust -->|PLACED_BOOKING| Book
    Book -->|BOOKED_ON| Voyage
    Book -.->|ROLLED_TO| Voyage

    Inc -.->|AFFECTS_VESSEL| Vessel

    Org -->|BASED_AT| Port

    %% Message Sender Edges
    Msg -.->|SENT_BY_VESSEL| Vessel
    Msg -.->|SENT_BY_ORG| Org
    Msg -.->|ISSUED_BY_MANAGER| TManager
    Msg -.->|SENT_BY_CUSTOMER| Cust

    %% Message Entity & Incident Edges
    Msg -.->|ABOUT_VESSEL / REFERENCES_VESSEL| Vessel
    Msg -.->|ABOUT_VOYAGE / REFERENCES_VOYAGE| Voyage
    Msg -.->|ABOUT_PORT_CALL| PCall
    Msg -.->|ABOUT_CLASS / REFERENCES_CLASS| VClass
    Msg -.->|REFERENCES_VESSEL_TYPE| VType
    Msg -.->|REFERENCES_MANAGER| TManager
    Msg -.->|EVENT_AT_PORT / REFERENCES_PORT| Port
    Msg -.->|REPORTS / CORROBORATES / REVISES / CORRECTS_INCIDENT| Inc
    Msg -.->|DESCRIBES_CONGESTION| Cong
    Msg -.->|REFERENCES_BOOKING| Book
    Msg -.->|REFERENCES_CUSTOMER| Cust
    Msg -.->|CORRECTS_MESSAGE / REFERENCES_MESSAGE| Msg
```

---

## 6. Cypher Schema Constraints & Indexes (Neo4j / Memgraph DDL)

```cypher
// Unique Node Identifier Constraints
CREATE CONSTRAINT unique_vessel_id IF NOT EXISTS FOR (v:Vessel) REQUIRE v.vessel_id IS UNIQUE;
CREATE CONSTRAINT unique_vessel_imo IF NOT EXISTS FOR (v:Vessel) REQUIRE v.imo IS UNIQUE;
CREATE CONSTRAINT unique_vessel_type IF NOT EXISTS FOR (t:VesselType) REQUIRE t.type_id IS UNIQUE;
CREATE CONSTRAINT unique_vessel_class IF NOT EXISTS FOR (c:VesselClass) REQUIRE c.class_id IS UNIQUE;
CREATE CONSTRAINT unique_tech_manager IF NOT EXISTS FOR (m:TechnicalManager) REQUIRE m.manager_id IS UNIQUE;
CREATE CONSTRAINT unique_port_code IF NOT EXISTS FOR (p:Port) REQUIRE p.port_code IS UNIQUE;
CREATE CONSTRAINT unique_voyage_id IF NOT EXISTS FOR (voy:Voyage) REQUIRE voy.voyage_id IS UNIQUE;
CREATE CONSTRAINT unique_call_id IF NOT EXISTS FOR (pc:PortCall) REQUIRE pc.call_id IS UNIQUE;
CREATE CONSTRAINT unique_incident_id IF NOT EXISTS FOR (i:Incident) REQUIRE i.incident_id IS UNIQUE;
CREATE CONSTRAINT unique_congestion_id IF NOT EXISTS FOR (cg:Congestion) REQUIRE cg.congestion_id IS UNIQUE;
CREATE CONSTRAINT unique_booking_id IF NOT EXISTS FOR (b:Booking) REQUIRE b.booking_id IS UNIQUE;
CREATE CONSTRAINT unique_customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE;
CREATE CONSTRAINT unique_org_id IF NOT EXISTS FOR (org:Organization) REQUIRE org.org_id IS UNIQUE;
CREATE CONSTRAINT unique_message_id IF NOT EXISTS FOR (msg:Message) REQUIRE msg.message_id IS UNIQUE;

// Performance Indexes for Operational Traversal & Temporal Search
CREATE INDEX voyage_arrival_utc_idx IF NOT EXISTS FOR (voy:Voyage) ON (voy.revised_eta_utc);
CREATE INDEX incident_reported_utc_idx IF NOT EXISTS FOR (i:Incident) ON (i.reported_utc);
CREATE INDEX congestion_date_utc_idx IF NOT EXISTS FOR (cg:Congestion) ON (cg.date_utc);
CREATE INDEX booking_delivery_date_idx IF NOT EXISTS FOR (b:Booking) ON (b.promised_delivery_date_utc);
CREATE INDEX message_sent_at_utc_idx IF NOT EXISTS FOR (msg:Message) ON (msg.sent_at_utc);
```
