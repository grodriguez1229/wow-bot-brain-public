Feature: A catalog of named scene specs
  As the eval substrate
  I want a registry of reusable, named scene definitions
  So that the CLI and the self-improvement loop can run the same fixed scenes
  reproducibly across runs

  Scenario: Looking up a scene by id
    Given the scene catalog
    When I look up the scene "westfall-lfg"
    Then I get a spec located in "Westfall"
    And the spec has at least 2 bots

  Scenario: Every catalogued scene is uniquely identified and runnable
    Given the scene catalog
    Then every scene has a unique id
    And every scene has at least one bot and a positive turn count

  Scenario: An unknown scene id is rejected clearly
    Given the scene catalog
    When I look up the scene "does-not-exist"
    Then a lookup error is raised

  Scenario: Every scene carries a tags list for later slicing
    Given the scene catalog
    Then every scene has a tags list
