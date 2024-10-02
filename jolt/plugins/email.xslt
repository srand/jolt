<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:variable name="Failures" select="jolt-manifest/task[result='FAILED']" />
  <xsl:variable name="Unstable" select="jolt-manifest/task[result='UNSTABLE']" />
  <xsl:variable name="FailuresAndUnstable"
    select="jolt-manifest/task[result='UNSTABLE' or result='FAILED']" />
  <xsl:variable name="Executed"
    select="jolt-manifest/task[result!='CANCELLED' and result!='SKIPPED']" />
  <xsl:variable name="Successful" select="jolt-manifest/task[result='SUCCESS']" />
  <xsl:variable name="Tasks" select="jolt-manifest/task" />
  <xsl:variable name="Goals" select="jolt-manifest/task[goal='true']" />
  <xsl:variable name="Hours" select="floor(jolt-manifest/duration div 3600)" />
  <xsl:variable name="Minutes" select="floor((jolt-manifest/duration mod 3600) div 60)" />
  <xsl:variable name="Seconds" select="floor(jolt-manifest/duration mod 60)" />

  <xsl:template match="/">
    <html>
      <head>
        <link rel="stylesheet" href="https://www.w3schools.com/w3css/4/w3.css" />
        <style type="text/css">
          pre {
          margin-bottom: 0px;
          margin-top: 0px;
          overflow-x: auto;
          white-space: pre-wrap;
          white-space: -moz-pre-wrap;
          white-space: -pre-wrap;
          white-space: -o-pre-wrap;
          word-wrap: break-word;
          }
          a {
          color: #f44336;
          }
          a.log {
          color: white;
          }
        </style>
      </head>
      <body>
        <table width="100%" bgcolor="#f1f1f1"
          style="border-bottom: 1px solid #c1c1c1; border-top: 1px solid #c1c1c1; fixed">
          <tr>
            <td>
              <table width="720" cellpadding="10px">
                <tr>
                  <td width="25%" align="center">
                    <xsl:choose>
                      <xsl:when test="count($Failures) > 0">
                        <h2 style="font-size: 50pt; color:#f44336;">FAIL</h2>
                      </xsl:when>
                      <xsl:otherwise>
                        <h2 style="font-size: 50pt; color:green;">PASS</h2>
                      </xsl:otherwise>
                    </xsl:choose>
                  </td>
                  <td width="25%" align="center" style="border-left: 1px solid #c0c0c0">
                    <table>
                      <tr>
                        <td width="100%" align="center">Completed</td>
                      </tr>
                      <tr>
                        <td align="center">
                          <h2>
                            <xsl:value-of select="count($Executed)" />
                          </h2>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td width="25%" align="center" style="border-left: 1px solid #c0c0c0">
                    <table>
                      <tr>
                        <td width="100%" align="center">Failed</td>
                      </tr>
                      <tr>
                        <td align="center">
                          <h2>
                            <xsl:value-of select="count($FailuresAndUnstable)" />
                          </h2>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td width="25%" align="center" style="border-left: 1px solid #c0c0c0">
                    <table>
                      <tr>
                        <td width="100%" align="center">Duration</td>
                      </tr>
                      <tr>
                        <td align="center">
                          <h2>
                            <xsl:if test="$Hours > 0">
                              <xsl:value-of select="$Hours" />h </xsl:if>
                            <xsl:if test="$Minutes > 0">
                              <xsl:value-of select="$Minutes" />min </xsl:if>
                            <xsl:value-of
                              select="$Seconds" />s </h2>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>

        <xsl:choose>
          <xsl:when test="count($Failures) > 0">
            <p> This is an automated build report from Jolt. The build failed. <xsl:call-template
                name="jenkins-url" />
              <xsl:call-template name="gerrit-url" />
            </p>
          </xsl:when>
          <xsl:when test="count($Unstable) > 0 and count($Failures) = 0">
            <p> This is an automated build report from Jolt. The build was successful, but unstable
              task failures were ignored. <xsl:call-template name="jenkins-url" />
              <xsl:call-template
                name="gerrit-url" />
            </p>
          </xsl:when>
          <xsl:otherwise>
            <p> This is an automated build report from Jolt. The build was successful. <xsl:call-template
                name="jenkins-url" />
              <xsl:call-template name="gerrit-url" />
            </p>
          </xsl:otherwise>
        </xsl:choose>

        <xsl:for-each select="$Failures">
          <xsl:call-template name="task" />
        </xsl:for-each>

        <xsl:for-each select="$Unstable">
          <xsl:call-template name="task" />
        </xsl:for-each>

      </body>
    </html>
  </xsl:template>

  <xsl:template name="jenkins-url">
    <xsl:if test="jolt-manifest/parameter[@key='BUILD_URL']/@value != ''"> See <xsl:element name="a">
        <xsl:attribute name="href">
          <xsl:value-of select="jolt-manifest/parameter[@key='BUILD_URL']/@value" />
        </xsl:attribute>
      full build log </xsl:element> for details. </xsl:if>
  </xsl:template>

  <xsl:template name="gerrit-url">
    <xsl:if test="jolt-manifest/parameter[@key='GERRIT_URL']/@value != ''"> This <xsl:element
        name="a">
        <xsl:attribute name="href">
          <xsl:value-of select="jolt-manifest/parameter[@key='GERRIT_URL']/@value" />
        </xsl:attribute>
      Gerrit change </xsl:element> was built. </xsl:if>
  </xsl:template>

  <xsl:template name="task">
    <table width="100%" cellspacing="0" cellpadding="0" bgcolor="#f1f1f1">
      <xsl:element name="tr">
        <xsl:choose>
          <xsl:when test="result='FAILED'">
            <xsl:attribute name="bgcolor">#f44336</xsl:attribute>
          </xsl:when>
          <xsl:otherwise>
            <xsl:attribute name="bgcolor">#FF7E00</xsl:attribute>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:element>
      <td style="padding: 10px">
        <table cellpadding="0" cellspacing="0">
          <tr>
            <td width="100%" style="font-size: 16pt; color: white;">
              <xsl:value-of select="@name" />
            </td>
            <td>
              <xsl:if test="logstash != ''">
                <xsl:element name="a">
                  <xsl:attribute name="class">log</xsl:attribute>
                          <xsl:attribute name="href">
                    <xsl:value-of select="logstash" />
                  </xsl:attribute> Log </xsl:element>
              </xsl:if>
            </td>
          </tr>
        </table>
      </td>
      <xsl:element name="tr" />

      <xsl:for-each select="error">
        <tr>
          <td>
            <table width="100%">
              <tr>
                <td width="10%" style="padding: 5px; border-bottom: 1px solid #c1c1c1;">
                  <xsl:value-of select="type" />
                </td>
                <td width="90%"
                  style="padding: 5px; border-left: 1px solid #c1c1c1; border-bottom: 1px solid #c1c1c1;">
                  <xsl:value-of select="location" />
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding: 5px; border-bottom: 1px solid #c1c1c1;">
            <pre><xsl:value-of select="message"/></pre>
          </td>
        </tr>
        <xsl:if test="details != ''">
          <tr>
            <td style="padding: 5px;">
              <pre><xsl:value-of select="details"/></pre>
            </td>
          </tr>
        </xsl:if>
        <tr>
          <td style="padding: 0px; border-bottom: 2px solid #f44336;"></td>
        </tr>
      </xsl:for-each>

    </table>
    <br />
  </xsl:template>

</xsl:stylesheet>