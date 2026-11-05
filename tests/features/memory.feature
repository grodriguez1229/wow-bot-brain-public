Feature: Shared memory shapes bot behavior
  As the world-sim
  I want bots to hear nearby chatter and remember people
  So that scenes read as conversation, not broadcast

  Scenario: A bot's request carries the lines said just before it
    Given a recording fake brain
    And bots "Geysse" and "Lynea"
    When I run a 4-turn no-player scene with seed 2
    Then at least one brain call received non-empty recent_lines

  Scenario: Consolidation records a relationship note from a transcript
    Given a fresh memory db
    And a two-bot transcript where they agree to group up
    When I consolidate the scene with a canned summarizer
    Then "Geysse" remembers a note about "Lynea"
