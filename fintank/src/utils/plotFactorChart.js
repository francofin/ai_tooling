

export const factorCharter = (dataValues, dataLabels, factorLabel, factorText) => {

    const chartState = {
          
        series: [{
          name: factorLabel,
          data: dataValues
        }],
        options: {
          chart: {
            height: 400,
            type: 'bar',
          },
          plotOptions: {
            bar: {
              borderRadius: 10,
              dataLabels: {
                position: 'top',
              },
            }
          },
          dataLabels: {
            enabled: true,
            formatter: function (val) {
              return val + "%";
            },
            offsetY: -20,
            style: {
              fontSize: '14px',
              colors: ["#4e4e4e"]
            }
          },
          
          xaxis: {
            categories: dataLabels,
            position: 'top',
            axisBorder: {
              show: false
            },
            axisTicks: {
              show: false
            },
            crosshairs: {
              fill: {
                type: 'gradient',
                gradient: {
                  colorFrom: '#1a629d',
                  colorTo: '#1b87e0',
                  stops: [0, 100],
                  opacityFrom: 0.4,
                  opacityTo: 0.5,
                }
              }
            },
            tooltip: {
              enabled: true,
            }
          },
          yaxis: {
            axisBorder: {
              show: false
            },
            axisTicks: {
              show: false,
            },
            labels: {
              show: false,
              formatter: function (val) {
                return val + "%";
              }
            }
          
          },
          title: {
            text: factorText,
            floating: false,
            offsetY: 0,
            align: 'center',
            style: {
              color: '#444'
            }
          }
        },
      };

      return chartState;

}