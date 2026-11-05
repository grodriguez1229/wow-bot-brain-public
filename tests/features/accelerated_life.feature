Feature: Accelerated-life harness compresses days of evolution
  As the evolution lab
  I want N days of (live a scene -> reflect) run offline against a fake brain
  So that I can watch identity accumulate without waiting real days

  Scenario: Running K days writes K trail records and accumulates identity
    Given a fresh memory db
    And a fake brain and a fake reflection that adds one facet per day
    When I run accelerated life for bot "Geysse" for 3 days
    Then the trail has 3 day records
    And bot "Geysse" has 3 identity facets

  Scenario: day_plan rotates and never pairs a bot with itself
    When I build day plans for bot "Geysse" for days 0 1 2 3 4
    Then no day plan has partner "Geysse"
    And at least two distinct locations appear
