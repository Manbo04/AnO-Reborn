import lxml.html
table_html = """<table class="templatetable inverttable ">
                        <tr>
                            <th><span class="material-icons-outlined ">
                                    account_balance
                                            </span>{{ name }}</th>
                        </tr>
                        <tr>
                            <td><span class="material-icons-outlined ">
                                            people_alt
                                            </span>Population:</td>
                            <td>{{ population }}</td>
                        </tr>
                        <tr>
                            <td><span class="material-icons-outlined">
                                power
                                </span>Powered:</td>
                            {% if energy > 0 %}
                            <td>Yes</td>
                            {% else %}
                            <td>No</td>
                            {% endif %}
                        </tr>
                    </table>"""
tree = lxml.html.fragment_fromstring(table_html)
for row in tree.findall('.//tr'):
    print(len(row.findall('.//td')))
