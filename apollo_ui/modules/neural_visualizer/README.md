# Apollo Neural Visualizer

This module visualizes the neural network created by Apollo's `neural_learning`
module.

## Requirements

Install both modules:

- `neural_learning`
- `neural_visualizer`

Train the Neural Learning module first.

The visualizer then reads:

`Apollo/storage/neural_learning_state.json`

## What it shows

- active words and word-pair input features
- strongest hidden-neuron activations
- output labels
- confidence percentages
- strongest input -> hidden connections
- strongest hidden -> output connections
- whether the neural model passed Apollo's quality gate

## Apollo tools

- `neural_visualizer.visual_neural_status`
- `neural_visualizer.visualize_input`

## UI

The module supports Apollo's dynamic module UI.

Default:

`Apps -> Neural Visualizer`

You can move it to a direct sidebar tab from:

`Modules -> Neural Visualizer -> Selected Module UI -> Sidebar Tab`
