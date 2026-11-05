Feature: The optimizer run log
  As the loop's audit trail
  I want each cycle appended as one record
  So that the whole run is reconstructable after the fact

  Scenario: Records append and read back in order
    Given an empty run log
    When I append a kept cycle 1 "raise warmth in chat prompt" eval 2.0 to 2.8
    And I append a reverted cycle 2 "shorten tick prompt" eval 2.8 to 2.9
    Then the log has 2 records
    And record 1 is kept with commit not empty
    And record 2 is not kept
