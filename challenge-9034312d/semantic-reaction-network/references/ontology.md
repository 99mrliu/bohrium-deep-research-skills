# Scientific semantic ontology

## Meaning is not geometry

A node is a scientific or technical participant; an edge is a source-supported proposition with a type and direction. Ports constrain legal propositions. Coordinates are deterministic display choices only. An arrowhead never supplies missing evidence.

## Compartments

A compartment is a source-supported physical location or explicitly defined pipeline domain (for example extracellular space, cytosol, reactor, detection pipeline). Do not invent subcellular localization. Assign every entity, process, and measurement node to a declared compartment; a chart is a data display and need not have one. Prefer a neutral `unspecified_location` compartment with an uncertainty rather than guessing.

## Node kinds

- `entity`: molecule, complex, material, organism component, reagent, catalyst, substrate/product, waste, or apparatus component. `entity_type` refines it. Catalysis sources must explicitly be `enzyme` or `catalyst`.
- `process`: transformation, reaction, assay operation, experimental step, or route task. Sequence and catalysis terminate at processes, not at arbitrary drawings.
- `measurement`: observation/readout operation with a measured property. It is not the material being measured.
- `chart`: a presentation of actual tabular records, never a decorative trend invented by an LLM.

## Edge kinds and legal semantics

| Kind | Meaning and principal endpoints | Carrier | Required visual distinction |
|---|---|---|---|
| `material_flow` | Entity enters process, process yields entity, or direct entity transfer within a compartment | material | Solid directed material arrow |
| `transport` | Entity relocation from one declared compartment to another | material | Transport arrow, source/target compartments differ |
| `sequence` | Process/measurement step precedes another | control | Dashed sequence arrow; not a chemical reaction |
| `activation` | Source-supported positive regulation of an entity/process | signal | Open activation arrow plus `+`; no generic arrow |
| `inhibition` | Source-supported negative regulation of an entity/process | signal | Blunt red bar; no generic arrowhead |
| `catalysis` | Enzyme/catalyst entity facilitates a process | signal | Dotted catalysis mark; it is not substrate flow |
| `measurement` | An entity/process/readout supplies observed data to a measurement or chart | data | Dashed data link with open circle |

A legal endpoint pattern alone does not establish truth: evidence is separately mandatory. For example, an inhibitor connected to a conversion is not necessarily competitive inhibition. If only inhibition is supported, do not add a molecular mechanism. If only association is stated and this ontology has no evidenced causal interpretation, retain an uncertainty and omit the edge rather than relabelling it.

## Ports

Every edge resolves `{node, port}` at both ends. An output port connects only to an input port. Carriers are `material`, `control`, `signal`, and `data`. Port type compatibility catches regulation disguised as material flow and measurements connected to material ports. Port names are stable editable identifiers, not evidence.

## Phases

`phase` labels belong to nodes/edges; `phase_dependencies` encode sourced `from_phase -> to_phase` ordering. Do not use sequence arrows merely to beautify a route. Experimental phase dependencies form an acyclic partial order. Return/recycle topology belongs in semantic feedback, not an accidental cycle among phases.

## Branch, join, split logic

For two or more same-family material links leaving a node or sequence links leaving a step, declare a `branch` with the exact edge set and `all`, `any`, or `xor` mode. For corresponding fan-in, declare a `join`. `xor` requires a source-supported condition on each alternative edge. Undeclared branch/joins are semantic errors even if lines look tidy. A reaction with multiple substrate inputs requires an evidenced material join rather than an implicit assumption that any substrate suffices.

## Feedback and cycles

Set `feedback: true` only when the source supports feedback/recycle and the edge participates in a directed cycle. Removing all feedback edges must eliminate every directed cycle. This prevents one decorative feedback label from excusing unrelated accidental cycles. Negative inhibition alone is not proof of feedback. Sequence/measurement/data flow should not silently create a biological cycle.
