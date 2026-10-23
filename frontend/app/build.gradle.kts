plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.example.teamapp"
    // Explicit live acceptance writes only dedicated test accounts/families.
    // The ordinary instrumentation suite remains unchanged unless opted in.
    if (providers.gradleProperty("magicvvuSharedCloudTest").orNull == "true") {
        sourceSets.getByName("androidTest").apply {
            java.directories.clear()
            kotlin.directories.clear()
            kotlin.directories.add("src/sharedCloudTest/java")
        }
    }
    compileSdk {
        version = release(37) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.example.teamapp"
        minSdk = 24
        targetSdk = 36
        versionCode = 3
        versionName = "1.1.1-test"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            val isolated = providers.gradleProperty("magicvvuIsolatedTest").orNull == "true"
            val testUrl = providers.gradleProperty("magicvvuApiUrl")
                .orElse(if (isolated) "http://10.0.2.2:18081" else "https://8.134.172.165:8000").get()
            require(!testUrl.contains('"') && !testUrl.contains('\\') && !testUrl.contains('\n') && !testUrl.contains('\r')) { "Invalid test API origin" }
            buildConfigField("boolean", "CLOUD_EXPECT_ISOLATED", isolated.toString())
            buildConfigField("String", "CLOUD_API_URL", "\"$testUrl\"")
        }
        release {
            buildConfigField("boolean", "CLOUD_EXPECT_ISOLATED", "false")
            val releaseUrl = providers.gradleProperty("mewstowReleaseApiUrl").orElse("").get()
            require(releaseUrl.isEmpty() || (releaseUrl.startsWith("https://") && !releaseUrl.contains('"') && !releaseUrl.contains('\\') && !releaseUrl.contains('\n') && !releaseUrl.contains('\r'))) { "Release API must be a configured HTTPS origin" }
            buildConfigField("String", "CLOUD_API_URL", "\"$releaseUrl\"")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation("androidx.compose.material:material-icons-core")
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
}
