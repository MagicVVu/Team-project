package com.example.teamapp.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.example.teamapp.R
import com.example.teamapp.ui.theme.LocalLightDesign

/** Approved V1: separate letters, cat-ear M, box o, and the double-tail w. */
@Composable
internal fun MewstowWordmark(modifier: Modifier = Modifier, outlined: Boolean = false) {
    val dark = !LocalLightDesign.current
    val painter = painterResource(R.drawable.mewstow_wordmark)
    val imageModifier = Modifier.fillMaxSize()
        .padding(horizontal = if (dark) 8.dp else 0.dp, vertical = 3.dp)
    Box(
        modifier.clip(RoundedCornerShape(8.dp))
            .background(if (dark) Color(0xFFFFF5CF) else Color.Transparent),
        contentAlignment = Alignment.CenterStart
    ) {
        if (outlined) {
            // Offset alpha silhouettes follow the lettering, not the rectangular image bounds.
            // One shared painter preserves the approved V1 artwork and its two green colors.
            for ((x, y) in listOf(-1 to -1, 0 to -1, 1 to -1, -1 to 0,
                1 to 0, -1 to 1, 0 to 1, 1 to 1)) {
                Image(painter, contentDescription = null, contentScale = ContentScale.Fit,
                    colorFilter = ColorFilter.tint(Color(0xFFFFFDF7)),
                    modifier = Modifier.offset(x.dp, y.dp).then(imageModifier))
            }
        }
        Image(
            painter,
            contentDescription = stringResource(R.string.app_name),
            contentScale = ContentScale.Fit,
            modifier = imageModifier
        )
    }
}

@Composable
internal fun MewstowMark(modifier: Modifier = Modifier) {
    Image(painterResource(R.drawable.mewstow_mark), contentDescription = null,
        contentScale = ContentScale.Fit, modifier = modifier)
}
