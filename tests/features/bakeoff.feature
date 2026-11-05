Feature: Model bake-off bookkeeping
  As the model-comparison harness
  I want each model's score and speed recorded, and a viable winner chosen
  So that a model swap is an evidence-based reset of the baseline, not a guess

  Scenario: A recorded row round-trips through the log
    Given a bake-off row for "mistral-small:22b" eval 2.6 seconds-per-scene 40.0
    When I write it and read the log back
    Then the log has 1 row for "mistral-small:22b" with eval 2.6

  Scenario: The strongest viable model wins
    Given a logged row "qwen3.5:9b" eval 1.98 seconds-per-scene 12.0
    And a logged row "gemma4:latest" eval 2.30 seconds-per-scene 20.0
    And a logged row "mistral-small:22b" eval 2.75 seconds-per-scene 45.0
    When I pick the winner over baseline "qwen3.5:9b" eval 1.98 margin 0.5 max-seconds 90.0
    Then the winner is "mistral-small:22b"

  Scenario: A model that does not clear the margin loses to the baseline
    Given a logged row "qwen3.5:9b" eval 1.98 seconds-per-scene 12.0
    And a logged row "gemma4:latest" eval 2.30 seconds-per-scene 20.0
    When I pick the winner over baseline "qwen3.5:9b" eval 1.98 margin 0.5 max-seconds 90.0
    Then the winner is "qwen3.5:9b"

  Scenario: A strong but too-slow model is rejected as non-viable
    Given a logged row "qwen3.5:9b" eval 1.98 seconds-per-scene 12.0
    And a logged row "mistral-small:22b" eval 2.90 seconds-per-scene 120.0
    When I pick the winner over baseline "qwen3.5:9b" eval 1.98 margin 0.5 max-seconds 90.0
    Then the winner is "qwen3.5:9b"
