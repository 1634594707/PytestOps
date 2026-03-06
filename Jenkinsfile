pipeline {
  agent any

  stages {
    stage('Install') {
      steps {
        sh 'python -m pip install --upgrade pip'
        sh 'python -m pip install -e .[dev]'
      }
    }

    stage('Quality') {
      steps {
        sh 'ruff check ntf tests'
        sh 'mypy ntf'
      }
    }

    stage('Test') {
      steps {
        sh 'pytest -q'
      }
      post {
        always {
          archiveArtifacts artifacts: 'report/**', allowEmptyArchive: true
        }
      }
    }

    stage('Build') {
      steps {
        sh 'python -m build'
      }
      post {
        always {
          archiveArtifacts artifacts: 'dist/**', allowEmptyArchive: true
        }
      }
    }
  }
}
