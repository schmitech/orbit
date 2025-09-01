ThisBuild / scalaVersion := "2.13.12"

lazy val root = (project in file(".")).settings(
  name := "orbit-scala-client"
)

libraryDependencies += "junit" % "junit" % "4.13.2" % Test

