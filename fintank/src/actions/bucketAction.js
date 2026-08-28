import swal from 'sweetalert';


const bucketAction = async (bucketData, bucketKeys, bucketName, indexName, factorName) => {
    console.log(bucketData)

    return{
        type:'showbucket',
        payload:{
            bucketData,
            bucketKeys,
            bucketName,
            indexName,
            factorName
        }
    }
}


export default bucketAction