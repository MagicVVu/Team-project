package com.example.teamapp.data

/** Team distribution credential; deliberately versioned for shared test builds.
 * This proves possession only. User login and household permissions remain separate.
 */
internal object TeamApiAccess {
    const val HEADER = "X-MagicVVu-App-Key"
    const val KEY = "4d2e16efa734ef34a305c5543f1f723a849be98e569da8840e20ec9809b827b7"
}
