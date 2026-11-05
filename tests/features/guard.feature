Feature: Edit whitelist guard
  As the loop's blast-radius limiter
  I want any change outside the allowed config files flagged
  So that a cycle can never touch C++, the prod DB, or unrelated code

  Scenario: An in-scope edit is allowed
    Given changed paths "prompts.py","personality.py"
    Then no paths are out of scope

  Scenario: An out-of-scope edit is flagged
    Given changed paths "prompts.py","sim/scene_runner.py","main.py"
    Then the out-of-scope paths are "sim/scene_runner.py","main.py"
