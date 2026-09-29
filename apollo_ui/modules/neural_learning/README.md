# Neural Learning Module

A small real one-hidden-layer neural network implemented in pure Python.

It learns labelled text examples such as:

- `hello there` -> `greeting`
- `make a Python file` -> `coding`
- `check my car` -> `vehicle`

Tools:

- `add_training_example`
- `train_network`
- `predict_label`
- `neural_status`
- `list_training_examples`

Persistent state:

`storage/neural_learning_state.json`

This auxiliary network does NOT replace or retrain Qwen/Ollama. It gives Apollo
a small user-trainable pattern classifier alongside the main local LLM.
