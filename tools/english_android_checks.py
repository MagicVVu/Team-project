"""Compile Android and run its JVM suite with a Unicode-safe relative classpath."""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT/'frontend';CACHE=ROOT/'.cache/english-jvm';REPORT=ROOT/'reports/ai-english'


def main():
    CACHE.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    init=r'''
import groovy.json.JsonOutput
allprojects { p ->
 if (p.path == ':app') {
  p.tasks.register('exportAssistantTestClasspath') {
   dependsOn('compileDebugUnitTestKotlin')
   doLast {
    def out = new File(p.rootDir, '../.cache/english-jvm/classpath.json')
    out.text = JsonOutput.toJson(p.tasks.getByName('testDebugUnitTest').classpath.files.collect { it.absolutePath })
   }
  }
 }
}
'''
    (CACHE/'export.gradle').write_text(init,encoding='utf-8')
    env={**os.environ,'JAVA_HOME':'D:/Android/jdk21','ANDROID_HOME':'D:/AnSDK'}
    command=[str(FRONT/'gradlew.bat'),'-I','../.cache/english-jvm/export.gradle',':app:bundleDebugClassesToRuntimeJar',':app:exportAssistantTestClasspath','--offline','--no-daemon']
    compiled=subprocess.run(command,cwd=FRONT,env=env,capture_output=True,timeout=300)
    (REPORT/'android-compile.log').write_bytes(compiled.stdout+compiled.stderr)
    if compiled.returncode:raise SystemExit('ANDROID_COMPILE_FAILED; see local log')
    paths=json.loads((CACHE/'classpath.json').read_text())
    paths=[os.path.relpath(Path(p),FRONT) if Path(p).is_relative_to(ROOT) else p for p in paths]
    classes=['com.example.teamapp.'+p.stem for p in (FRONT/'app/src/test/java/com/example/teamapp').glob('*Test.kt')]
    args='-Dfile.encoding=UTF-8\n-Dsun.stdout.encoding=UTF-8\n-Dsun.stderr.encoding=UTF-8\n-cp\n"'+os.pathsep.join(paths).replace('\\','\\\\').replace('"','\\"')+'"\norg.junit.runner.JUnitCore\n'+'\n'.join(classes)+'\n'
    (CACHE/'run.args').write_text(args,encoding='utf-8')
    result=subprocess.run([env['JAVA_HOME']+'/bin/java.exe','@../.cache/english-jvm/run.args'],cwd=FRONT,capture_output=True,timeout=60)
    output=(result.stdout+result.stderr).decode('utf-8',errors='replace')
    (REPORT/'android-junit.log').write_text(output,encoding='utf-8')
    match=re.search(r'OK \((\d+) tests?\)',output)
    summary={'android_compile':compiled.returncode==0,'jvm_runner':'JUnitCore using Gradle exported dependencies',
        'passed':int(match[1]) if match else 0,'failed':result.returncode!=0,'gradle_test_worker_passed':False,
        'gradle_test_worker_issue':'ClassNotFoundException in Gradle worker on this workspace; direct JUnit used',
        'device_tests_run':False,'app_joint_acceptance':False,'server_accessed':False}
    (REPORT/'android-tests.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))
    if result.returncode:raise SystemExit(1)


if __name__=='__main__':main()
