/**
 * Bharat Core Services — agents built for India, hosted together in the
 * `bharat-core-cuga-agent-app` Code Engine app. That app is EXTERNAL to the all-in-one:
 * its own repo, image, secret and sign-in (see build/external/apps/bharat-core-cuga-agent-app.conf).
 *
 * Each entry becomes a row in the "Bharat Core Services" list on the home page.
 * To add a service: add an entry here with the path it is served at inside
 * bharat-core-cuga-agent-app. No other UI change is needed.
 */
export interface BharatService {
  id: string
  /** Shown as the link text */
  name: string
  /** One or two plain sentences: what a user can do with it */
  description: string
  /** Short facts shown as chips */
  facts: string[]
  /** Code Engine app that serves it */
  ceApp: string
  /** Path inside that app ('/' for the app's home page) */
  path: string
  /** Where it runs on a laptop (`python main.py`) */
  localUrl: string
}

export const BHARAT_SERVICES: BharatService[] = [
  {
    id: 'farm-assistant',
    name: 'Farm Assistant (Voice agent)',
    description:
      "Ask by voice or text in Hindi, Tamil, Telugu or another Indian language about FAO's guide to how women pastoralists, fishers and farmers work with land and water. Hear the answer back in the same language, with the pages it came from.",
    facts: ['11 languages', 'Sarvam speech', 'bring your Sarvam key'],
    ceApp: 'bharat-core-cuga-agent-app',
    path: '/',
    localUrl: 'http://localhost:28831/',
  },
]
