package com.example.teamapp.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import com.example.teamapp.data.StockItem
import com.example.teamapp.data.loadPhotoBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Photos remain their original colors in either theme; unavailable photos use the native icon. */
@Composable
internal fun StockItemImage(item: StockItem, modifier: Modifier, fallback: @Composable () -> Unit) {
    val context = LocalContext.current
    val bitmap by produceState<Bitmap?>(null, item.image) {
        value = null
        value = withContext(Dispatchers.IO) { loadPhotoBitmap(context, item.image, 256) }
    }
    Box(modifier) {
        val photo = bitmap
        if (photo == null) fallback()
        else Image(photo.asImageBitmap(), item.name, Modifier.fillMaxSize().testTag("item-photo-${item.id}"), contentScale = ContentScale.Fit)
    }
}
