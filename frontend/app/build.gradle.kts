plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.example.teamapp"
    compileSdk {
        version = release(37) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.example.teamapp"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            buildConfigField("boolean", "CLOUD_EXPECT_ISOLATED", "true")
            buildConfigField("String", "CLOUD_API_URL", "\"${providers.gradleProperty("magicvvuApiUrl").orElse("http://10.0.2.2:18080").get()}\"")
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
        create("internal") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".internal"
            versionNameSuffix = "-internal"
            // A separate team build, explicitly bound to the shared server over TLS.
            buildConfigField("String", "CLOUD_API_URL", "\"https://8.134.172.165:8000\"")
            buildConfigField("boolean", "CLOUD_EXPECT_ISOLATED", "false")
            matchingFallbacks += listOf("debug")
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
